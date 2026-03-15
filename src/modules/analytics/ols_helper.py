class OLSHelper:
    @staticmethod
    def calculate_linear_regression(x: list[float], y: list[float]):
        """
        Calcula os coeficientes da regressão linear simples (y = mx + b)
        usando o Método dos Mínimos Quadrados Clássico.
        Retorna m, b, r2.
        """
        if not x or not y or len(x) != len(y) or len(x) < 2:
            return 0.0, 0.0, 0.0
            
        n = len(x)
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(x_i * y_i for x_i, y_i in zip(x, y))
        sum_x2 = sum(x_i ** 2 for x_i in x)
        
        denominator = (n * sum_x2 - sum_x ** 2)
        if denominator == 0:
            return 0.0, 0.0, 0.0
            
        m = (n * sum_xy - sum_x * sum_y) / denominator
        b = (sum_y - m * sum_x) / n
        
        # Calcular R^2
        mean_y = sum_y / n
        ss_tot = sum((y_i - mean_y) ** 2 for y_i in y)
        ss_res = sum((y_i - (m * x_i + b)) ** 2 for x_i, y_i in zip(x, y))
        
        r2 = 1.0 - (ss_res / ss_tot) if ss_tot != 0 else 0.0
        # Corrigindo R2 que pode dar levemente negativo por float error
        if r2 < 0:
            r2 = 0.0
            
        return m, b, r2

