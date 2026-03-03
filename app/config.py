import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("JOB_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("No BOT_TOKEN found in environment variables")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

DB_CONFIG = {
    "host": os.getenv("DDB_HOST", "localhost"),
    "port": int(os.getenv("DDB_PORT", 5432)),
    "database": os.getenv("DDB_NAME", "job_bot_db"),
    "user": os.getenv("DDB_USER", "postgres"),
    "password": os.getenv("DDB_PASSWORD", ""),
}