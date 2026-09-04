"""
EmailService — envio transacional via smtplib.

Ambiente de desenvolvimento: Mailhog (SMTP_HOST=mailhog, SMTP_PORT=1025).
Produção (Hostinger): configurar SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM.
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from src.shared.utils.environment import environment
from src.shared.utils.logger import logger

_SMTP_HOST = environment.get("SMTP_HOST", "mailhog")
_SMTP_PORT = int(environment.get("SMTP_PORT", "1025"))
_SMTP_USER = environment.get("SMTP_USER", "")
_SMTP_PASSWORD = environment.get("SMTP_PASSWORD", "")
_SMTP_FROM = environment.get("SMTP_FROM", "noreply@monettra.app")
_SMTP_USE_TLS = environment.get("SMTP_USE_TLS", "false").lower() == "true"


class EmailService:
    def send_invite(self, to_email: str, invite_link: str, account_name: str) -> bool:
        """
        Envia e-mail de convite com link de cadastro.
        Retorna True em caso de sucesso, False em falha (falha silenciosa para não travar o fluxo).
        """
        subject = f"Você foi convidado para a conta {account_name} no Monettra"
        html_body = f"""
        <html>
          <body style="font-family: Georgia, serif; background: #f5f0e8; padding: 32px;">
            <div style="max-width: 560px; margin: 0 auto; background: #faf7f2;
                        border: 1px solid #c4a35a; border-radius: 8px; padding: 32px;">
              <h2 style="color: #8b6914; font-family: Cinzel, Georgia, serif;">
                Convite Monettra
              </h2>
              <p style="color: #3b2f20;">
                Você foi convidado para participar da conta
                <strong>{account_name}</strong> no Monettra.
              </p>
              <p style="color: #3b2f20;">
                Clique no botão abaixo para criar sua conta e aceitar o convite.
                Este link é válido por <strong>24 horas</strong>.
              </p>
              <a href="{invite_link}"
                 style="display: inline-block; margin-top: 16px; padding: 12px 24px;
                        background: #8b6914; color: #faf7f2; text-decoration: none;
                        border-radius: 6px; font-weight: bold;">
                Aceitar convite
              </a>
              <p style="margin-top: 24px; font-size: 12px; color: #7a6a55;">
                Se você não esperava este convite, pode ignorar este e-mail com segurança.
              </p>
            </div>
          </body>
        </html>
        """
        return self._send(to_email, subject, html_body)

    def _send(self, to_email: str, subject: str, html_body: str) -> bool:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = _SMTP_FROM
        msg["To"] = to_email
        msg.attach(MIMEText(html_body, "html"))

        try:
            if _SMTP_USE_TLS:
                with smtplib.SMTP_SSL(_SMTP_HOST, _SMTP_PORT) as server:
                    if _SMTP_USER and _SMTP_PASSWORD:
                        server.login(_SMTP_USER, _SMTP_PASSWORD)
                    server.sendmail(_SMTP_FROM, to_email, msg.as_string())
            else:
                with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT) as server:
                    if _SMTP_USER and _SMTP_PASSWORD:
                        server.login(_SMTP_USER, _SMTP_PASSWORD)
                    server.sendmail(_SMTP_FROM, to_email, msg.as_string())
            logger.info(f"[EmailService] E-mail enviado para {to_email} — assunto: {subject}")
            return True
        except Exception as exc:
            logger.warning(f"[EmailService] Falha ao enviar e-mail para {to_email}: {exc}")
            return False
