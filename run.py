import os
import sys
import subprocess
import venv
import logging
import shutil
import time
import ctypes

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run_cmd(cmd, shell=True, capture_output=True):
    try:
        result = subprocess.run(cmd, shell=shell, capture_output=capture_output, text=True)
        return result
    except Exception as e:
        return None

def check_service(service_name):
    """Checks if a Windows service is running."""
    res = run_cmd(f"sc query {service_name}")
    if res and "STATE" in res.stdout:
        return "RUNNING" in res.stdout, True
    return False, False

def start_service(service_name):
    if not is_admin():
        logger.error(f"Cannot start {service_name} without Administrator privileges.")
        return False
    logger.info(f"Attempting to start {service_name}...")
    res = run_cmd(f"powershell -Command \"Start-Service {service_name}\"")
    return res and res.returncode == 0

def ensure_dependencies():
    """Ensures MySQL and Redis are running."""
    if sys.platform != "win32":
        return

    # 1. Redis
    redis_found = False
    for s in ["redis", "Redis"]:
        is_running, exists = check_service(s)
        if exists:
            redis_found = True
            if not is_running:
                start_service(s)
            break
    
    if not redis_found:
        logger.warning("!!! Redis service NOT FOUND !!!")
        logger.info("Please install Redis: https://github.com/tporadowski/redis/releases")

    # 2. PostgreSQL
    pg_found = False
    # Common service names for PostgreSQL on Windows
    pg_services = ["postgresql-x64-18", "postgresql-x64-16", "postgresql-x64-15", "postgres"]
    for s in pg_services:
        is_running, exists = check_service(s)
        if exists:
            pg_found = True
            if not is_running:
                start_service(s)
            break
    
    if not pg_found:
        logger.warning("!!! PostgreSQL service NOT FOUND !!!")
        logger.info("To install PostgreSQL: https://www.postgresql.org/download/windows/")
        
        if shutil.which("winget"):
            logger.info("Try running: winget install PostgreSQL.PostgreSQL.16")
        else:
            logger.info("winget not found. Please install PostgreSQL manually.")

def setup_venv():
    if not os.path.exists(".venv"):
        logger.info("Creating virtual environment...")
        venv.create(".venv", with_pip=True)
    
def get_python_exe():
    if sys.platform == "win32":
        return os.path.join(".venv", "Scripts", "python.exe")
    return os.path.join(".venv", "bin", "python")

def sync_env():
    if not os.path.exists(".env"):
        if os.path.exists(".env.example"):
            shutil.copy(".env.example", ".env")
            logger.info("Created .env from .env.example. PLEASE UPDATE YOUR BOT_TOKEN.")
        else:
            logger.error(".env.example missing!")
            sys.exit(1)

def run_migrations(python_exe):
    logger.info("Syncing database schema...")
    try:
        subprocess.run([python_exe, "-m", "alembic", "upgrade", "head"], check=True)
        logger.info("Schema sync successful.")
    except Exception as e:
        logger.warning(f"Schema sync FAILED: {e}")
        logger.info("Attempting to create database 'quizbot' if psql is in path...")
        # Note: postgres -c "CREATE DATABASE quizbot" might require admin/root. 
        # On local Windows, psql or createdb usually works if in path.
        run_cmd("createdb -U postgres quizbot")
        # Try migration again
        try:
            subprocess.run([python_exe, "-m", "alembic", "upgrade", "head"], check=True)
            logger.info("Schema sync successful after database creation attempt.")
        except Exception as e_retry:
             logger.error(f"Migration failed even after attempt to create DB: {e_retry}")
             logger.info("Make sure PostgreSQL is running and the database 'quizbot' exists or can be created.")

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    if not is_admin():
        logger.warning("Note: Running without Administrator privileges. Service management may fail.")

    ensure_dependencies()
    setup_venv()
    python_exe = get_python_exe()
    
    logger.info("Installing requirements...")
    try:
        subprocess.check_call([python_exe, "-m", "pip", "install", "-r", "requirements.txt"])
    except:
        logger.error("Failed to install dependencies.")
        sys.exit(1)

    sync_env()
    run_migrations(python_exe)
    
    if os.path.exists("main.py"):
        logger.info("Launching QuizBot...")
        try:
            subprocess.check_call([python_exe, "main.py"])
        except KeyboardInterrupt:
            logger.info("Shutting down.")
    else:
        logger.error("main.py not found!")
