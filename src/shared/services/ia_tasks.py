"""
ia_tasks.py — Celery Tasks compartilhadas do Motor de IA do Monettra.

Tasks assíncronas que rodam em processo separado (celery-worker),
desacopladas do event loop do FastAPI.

Posicionado no shared layer para permitir reutilização por outros módulos
sem criar dependências circulares entre domínios.
"""

import io
import json
import time  # noqa: F401 — mantido para compatibilidade futura com retries manuais
from datetime import datetime, timezone
from uuid import UUID as PyUUID

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.shared.services.celery_app import celery_app
from src.shared.services.ia_service import IaService
from src.shared.services.redis_service import RedisService
from src.shared.utils.environment import environment
from src.shared.utils.logger import logger
from src.repository.ofx_import_repository import OfxImportRepository
from src.repository.transaction_repository import TransactionRepository
from src.repository.category_repository import CategoryRepository
from src.schemas.transactions import TransactionType

from ofxtools.Parser import OFXTree


# ---------------------------------------------------------------------------
# System Prompt de Classificação OFX (Structured Outputs)
# ---------------------------------------------------------------------------
OFX_CLASSIFICATION_PROMPT = """Você é o "Escriba Real do Monettra", especialista em \
inteligência financeira e processamento de dados bancários. Classifique as transações \
recebidas conforme as instruções abaixo.

## Categorias Disponíveis:
{categories}

## Instruções de Processamento:
1. **Limpeza de Nome (cleaned_name)**: Remova prefixos e sufixos inúteis como "PG *", \
"SAO PAULO BR", "CARTÃO", "COMPRA", "WWW.", "Pix enviado:", "Pix recebido:", \
"Compra no débito:", "Compra no debito:", "No estabelecimento", "Pagamento efetuado:", \
"Pagamento de Titulo", "Pagamento de Convenio:", "Transferencia recebida:", \
"CP :", "Aplicacao:" ou códigos de transação. Deixe apenas o nome comercial legível.
2. **Categorização (category_code)**: Use o `code` (UUID) da categoria mais adequada. \
Use null se nenhuma se aplicar.
3. **Assinatura (is_subscription)**: true se for serviço recorrente (Netflix, Spotify, etc).
4. **Confiança (confidence)**: valor de 0.0 a 1.0.

## Dicas de Tipo (complementam — não substituem — o sinal do valor OFX):
- "Pix recebido", "Transferencia recebida" → hint: receita
- "Compra no débito/crédito", "Pix enviado", "Aplicacao", "Pagamento efetuado" → hint: despesa

## Regras Anti-Alucinação:
- Responda APENAS com o JSON no formato especificado.
- NÃO inclua explicações, markdown ou blocos de código.
- Preserve o `fitid` original de cada transação.
"""

# Structured Output Schema (OpenRouter json_schema)
OFX_CLASSIFICATION_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "ofx_classification",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "transactions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "fitid": {
                                "type": "string",
                                "description": "ID original da transação OFX",
                            },
                            "cleaned_name": {
                                "type": "string",
                                "description": "Nome comercial limpo",
                            },
                            "category_code": {
                                "type": ["string", "null"],
                                "description": "UUID da categoria ou null",
                            },
                            "is_subscription": {
                                "type": "boolean",
                                "description": "É serviço recorrente?",
                            },
                            "confidence": {
                                "type": "number",
                                "description": "Confiança de 0.0 a 1.0",
                            },
                        },
                        "required": [
                            "fitid",
                            "cleaned_name",
                            "category_code",
                            "is_subscription",
                            "confidence",
                        ],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["transactions"],
            "additionalProperties": False,
        },
    },
}

# Tamanho máximo de transações por chamada à IA (evita truncamento de JSON)
OFX_BATCH_SIZE = 30

# Palavras-chave para inferência de hint_type
_INCOME_KEYWORDS = (
    "pix recebido",
    "transferencia recebida",
    "transferência recebida",
    "credito recebido",
    "crédito recebido",
    "salario",
    "salário",
)
_EXPENSE_KEYWORDS = (
    "compra no débito",
    "compra no debito",
    "compra no crédito",
    "compra no credito",
    "pix enviado",
    "aplicacao",
    "aplicação",
    "pagamento efetuado",
    "pagamento de titulo",
    "pagamento de título",
    "pagamento de convenio",
    "pagamento de convênio",
)


# ---------------------------------------------------------------------------
# Helpers de DB para tasks (sessão própria — não herda do FastAPI)
# ---------------------------------------------------------------------------
def _create_db_session():
    """Cria sessão PostgreSQL independente para uso na Celery task."""
    db_config = {
        "dbname": environment.get("DATABASE_DB"),
        "user": environment.get("DATABASE_USER"),
        "password": environment.get("DATABASE_PASSWORD"),
        "host": environment.get("DATABASE_HOST"),
        "port": environment.get("DATABASE_PORT"),
    }
    url = (
        f"postgresql+psycopg://{db_config['user']}:{db_config['password']}"
        f"@{db_config['host']}:{db_config['port']}/{db_config['dbname']}"
    )
    engine = create_engine(url)
    Session = sessionmaker(bind=engine, autoflush=True, expire_on_commit=False)
    return Session()


def _sanitize_ofx(raw_bytes: bytes) -> OFXTree:
    """Parse e swap NAME/MEMO do conteúdo OFX."""
    parser = OFXTree()
    parser.parse(io.BytesIO(raw_bytes))
    root = parser.getroot()

    for transaction in root.iter("STMTTRN"):
        name = transaction.find("NAME")
        memo = transaction.find("MEMO")
        if name is None or memo is None:
            continue
        old_name_text = name.text
        name.text = memo.text
        if old_name_text:
            memo.text = old_name_text
            children = list(transaction)
            name_idx = children.index(name)
            memo_idx = children.index(memo)
            if name_idx > memo_idx:
                transaction.remove(name)
                transaction.insert(memo_idx, name)
        else:
            transaction.remove(memo)

    return parser


def _find_category_by_code(code_str, account_id: int, session):
    """Busca categoria pelo UUID code."""
    if not code_str or str(code_str).lower() == "null":
        return None
    try:
        cat_uuid = PyUUID(str(code_str))
        repo = CategoryRepository(dbSession=session)
        return repo.find_by_code(cat_uuid, account_id)
    except (ValueError, TypeError, AttributeError):
        logger.warning(f"OFX Task: category_code inválido: {code_str!r}")
        return None


def _get_hint_type(raw_description: str) -> str | None:
    """
    Infere hint_type ('income' | 'expense') a partir da descrição bruta OFX.
    Retorna None quando a descrição não corresponde a nenhum padrão conhecido.
    """
    desc_lower = raw_description.lower()
    for kw in _INCOME_KEYWORDS:
        if kw in desc_lower:
            return "income"
    for kw in _EXPENSE_KEYWORDS:
        if kw in desc_lower:
            return "expense"
    return None


# ---------------------------------------------------------------------------
# Celery Task — Processamento OFX em Background
# ---------------------------------------------------------------------------
@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    name="ia_engine.process_ofx",
)
def process_ofx_task(
    self,
    import_code: str,
    user_id: int,
    account_id: int,
    raw_bytes_hex: str,
):
    """
    Task Celery para processamento OFX em background.

    Roda em processo separado — não bloqueia o event loop do FastAPI.
    Cria sua própria sessão de banco para evitar conflito com o HTTP worker.
    """
    session = None
    try:
        session = _create_db_session()
        ia = IaService()

        ofx_repo = OfxImportRepository(dbSession=session)
        tx_repo = TransactionRepository(dbSession=session)
        cat_repo = CategoryRepository(dbSession=session)

        import_record = ofx_repo.find_by_code(import_code, account_id)
        if not import_record:
            logger.error(f"OFX Task {import_code}: registro não encontrado")
            return

        import_record.status = "processing"
        ofx_repo.update(import_record)

        raw_bytes = bytes.fromhex(raw_bytes_hex)

        # 1. Parse OFX
        parser = _sanitize_ofx(raw_bytes)
        ofx = parser.convert()
        all_transactions = []

        for statement in ofx.statements:
            for tx in statement.banktranlist:
                raw_desc = (tx.name or tx.memo or "Sem nome").strip()
                hint_type = _get_hint_type(raw_desc)
                all_transactions.append({
                    "fitid": tx.fitid,
                    "amount": float(tx.trnamt),
                    "date": tx.dtposted.strftime("%Y-%m-%d"),
                    "raw_description": raw_desc,
                    "hint_type": hint_type,
                })

        if not all_transactions:
            import_record.status = "completed"
            import_record.total_transactions = 0
            import_record.processed_transactions = 0
            ofx_repo.update(import_record)
            logger.info(f"OFX Task {import_code}: arquivo sem transações")
            return

        import_record.total_transactions = len(all_transactions)
        ofx_repo.update(import_record)
        logger.info(
            f"OFX Task {import_code}: {len(all_transactions)} transações para processar"
        )

        # 2. Busca categorias reais do usuário
        categories = cat_repo.find_all_by_account(account_id)
        categories_context = json.dumps([
            {
                "code": str(cat.code),
                "title": cat.title,
                "type": cat.type.value if cat.type else "expense",
            }
            for cat in categories
        ], ensure_ascii=False)

        # 3. Classificação IA com Structured Outputs (processada em lotes)
        system_prompt = OFX_CLASSIFICATION_PROMPT.format(
            categories=categories_context
        )

        total_batches = (len(all_transactions) + OFX_BATCH_SIZE - 1) // OFX_BATCH_SIZE
        logger.info(
            f"OFX Task {import_code}: chamando IA para classificar "
            f"{len(all_transactions)} transações em {total_batches} lote(s) "
            f"de até {OFX_BATCH_SIZE} itens"
        )

        classified_list = []
        for batch_idx in range(0, len(all_transactions), OFX_BATCH_SIZE):
            batch = all_transactions[batch_idx : batch_idx + OFX_BATCH_SIZE]
            batch_num = batch_idx // OFX_BATCH_SIZE + 1

            user_prompt = (
                "Classifique estas transações seguindo o schema JSON especificado:\n"
                + json.dumps(batch, ensure_ascii=False)
            )

            classified_data = ia.create_chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format=OFX_CLASSIFICATION_SCHEMA,
                max_tokens=8192,
            )

            logger.info(
                f"OFX Task {import_code}: lote {batch_num}/{total_batches} — "
                f"resposta IA tipo={type(classified_data).__name__}, "
                f"preview={str(classified_data)[:200]}"
            )

            if isinstance(classified_data, dict) and "transactions" in classified_data:
                batch_results = classified_data["transactions"]
                classified_list.extend(batch_results)
                logger.info(
                    f"OFX Task {import_code}: lote {batch_num}/{total_batches} — "
                    f"{len(batch_results)} transações classificadas"
                )
            elif classified_data is None:
                logger.warning(
                    f"OFX Task {import_code}: lote {batch_num}/{total_batches} — "
                    f"IA retornou None, lote importado sem classificação"
                )
            else:
                logger.warning(
                    f"OFX Task {import_code}: lote {batch_num}/{total_batches} — "
                    f"estrutura inesperada {type(classified_data)}, "
                    f"lote importado sem classificação"
                )

        logger.info(
            f"OFX Task {import_code}: {len(classified_list)} transações "
            f"classificadas no total pela IA"
        )

        # 4. Construção e persistência em lote
        records = []
        null_category_count = 0

        for tx_raw in all_transactions:
            ai_match = next(
                (c for c in classified_list if c.get("fitid") == tx_raw["fitid"]),
                None,
            )

            title = (
                ai_match.get("cleaned_name") or tx_raw["raw_description"]
                if ai_match else tx_raw["raw_description"]
            )

            category_id = None
            if ai_match:
                raw_cat_code = ai_match.get("category_code")
                if raw_cat_code and str(raw_cat_code).lower() != "null":
                    cat = _find_category_by_code(raw_cat_code, account_id, session)
                    if cat:
                        category_id = cat.id
                    else:
                        logger.warning(
                            f"OFX Task {import_code}: category_code "
                            f"{raw_cat_code!r} não encontrado no banco "
                            f"— fitid={tx_raw['fitid']}"
                        )

            if category_id is None:
                null_category_count += 1

            tx_type = (
                TransactionType.INCOME
                if tx_raw["amount"] > 0
                else TransactionType.EXPENSE
            )

            tx_date = datetime.strptime(tx_raw["date"], "%Y-%m-%d").date()

            records.append({
                "title": title,
                "amount": abs(int(tx_raw["amount"] * 100)),
                "type": tx_type,
                "due_date": tx_date,
                "description": tx_raw.get("raw_description"),
                "is_paid": True,
                "paid_at": datetime.now(timezone.utc),
                "user_id": user_id,
                "created_by": user_id,
                "account_id": account_id,
                "category_id": category_id,
            })

        logger.info(
            f"OFX Task {import_code}: {len(records)} registros — "
            f"{null_category_count} sem categoria"
        )

        if records:
            tx_repo.bulk_create(records)

        try:
            redis = RedisService()
            redis.delete_pattern(f"transactions:aid:{account_id}:*")
        except Exception as cache_err:
            logger.warning(f"OFX Task {import_code}: falha ao invalidar cache: {cache_err}")

        import_record.status = "completed"
        import_record.processed_transactions = len(records)
        ofx_repo.update(import_record)

        logger.info(
            f"OFX Task {import_code}: concluído com sucesso — "
            f"{len(records)} transações importadas"
        )

    except Exception as e:
        logger.error(f"OFX Task {import_code}: erro inesperado: {e}")
        try:
            if session:
                ofx_repo = OfxImportRepository(dbSession=lambda: session)
                import_record = ofx_repo.find_by_code(import_code, account_id)
                if import_record:
                    import_record.status = "error"
                    import_record.error_message = str(e)[:500]
                    ofx_repo.update(import_record)
        except Exception as inner_e:
            logger.error(f"OFX Task {import_code}: falha ao registrar erro: {inner_e}")

        try:
            raise self.retry(exc=e)
        except self.MaxRetriesExceededError:
            logger.error(
                f"OFX Task {import_code}: max retries atingido — task abandonada"
            )

    finally:
        if session:
            session.close()
