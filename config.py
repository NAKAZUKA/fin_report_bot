from dataclasses import dataclass
from dotenv import load_dotenv
import os

load_dotenv()

@dataclass
class InterfaxConfig:
    login: str
    password: str

@dataclass
class BotConfig:
    token: str
    interfax: InterfaxConfig
    interval_minutes: int

def load_config() -> BotConfig:
    return BotConfig(
        token=os.getenv("BOT_TOKEN", ""),
        interfax=InterfaxConfig(
            login=os.getenv("INTERFAX_LOGIN", ""),
            password=os.getenv("INTERFAX_PASSWORD", "")
        ),
        interval_minutes=int(os.getenv("DISPATCH_INTERVAL_MINUTES", "15"))
    )

