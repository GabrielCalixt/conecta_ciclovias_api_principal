import logging

# Um logger único para a aplicação. As mensagens vão para o console,
# que é onde o `docker compose logs` e o uvicorn mostram a saída.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

logger = logging.getLogger("conecta_ciclovias")
