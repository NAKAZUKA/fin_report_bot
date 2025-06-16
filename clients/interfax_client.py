from clients.interfax import InterfaxClient
from config import load_config

_config = load_config()

interfax_client = InterfaxClient(
    login=_config.interfax.login,
    password=_config.interfax.password
)


