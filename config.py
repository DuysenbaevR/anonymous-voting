import os
from typing import Optional

class Settings:
    """Настройки системы голосования"""
    
    # Основные настройки
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    
    # Безопасность
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-change-this-in-production")
    TOKEN_LENGTH: int = 32  # Длина токена в байтах
    TOKEN_EXPIRE_BUFFER_MINUTES: int = 5  # Буферное время после окончания голосования
    
    # Настройки голосования
    MIN_VOTING_DURATION_MINUTES: int = 1
    MAX_VOTING_DURATION_MINUTES: int = 30
    DEFAULT_VOTING_DURATION_MINUTES: int = 5
    
    # WebSocket настройки
    WEBSOCKET_HEARTBEAT_INTERVAL: int = 30  # секунды
    WEBSOCKET_RECONNECT_DELAY: int = 3  # секунды
    
    # Хранение данных
    USE_REDIS: bool = os.getenv("USE_REDIS", "false").lower() == "true"
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_PASSWORD: Optional[str] = os.getenv("REDIS_PASSWORD")
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    
    USE_POSTGRES: bool = os.getenv("USE_POSTGRES", "false").lower() == "true"
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", "5432"))
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "voting_user")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "password")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "voting_system")
    
    # Логирование
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = os.getenv("LOG_FILE", "logs/voting_system.log")
    
    # CORS настройки
    ALLOWED_ORIGINS: list = [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "https://localhost:8000",
        "https://127.0.0.1:8000",
    ]
    
    # Дополнительные origins из переменной окружения
    if os.getenv("ADDITIONAL_ORIGINS"):
        ALLOWED_ORIGINS.extend(os.getenv("ADDITIONAL_ORIGINS").split(","))
    
    # Настройки уведомлений (для будущего расширения)
    ENABLE_EMAIL_NOTIFICATIONS: bool = os.getenv("ENABLE_EMAIL_NOTIFICATIONS", "false").lower() == "true"
    ENABLE_SMS_NOTIFICATIONS: bool = os.getenv("ENABLE_SMS_NOTIFICATIONS", "false").lower() == "true"
    ENABLE_TELEGRAM_NOTIFICATIONS: bool = os.getenv("ENABLE_TELEGRAM_NOTIFICATIONS", "false").lower() == "true"
    
    # Email настройки
    SMTP_HOST: Optional[str] = os.getenv("SMTP_HOST")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME: Optional[str] = os.getenv("SMTP_USERNAME")
    SMTP_PASSWORD: Optional[str] = os.getenv("SMTP_PASSWORD")
    SMTP_USE_TLS: bool = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
    
    # Telegram настройки
    TELEGRAM_BOT_TOKEN: Optional[str] = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID: Optional[str] = os.getenv("TELEGRAM_CHAT_ID")
    
    # Статистика и аналитика
    ENABLE_ANALYTICS: bool = os.getenv("ENABLE_ANALYTICS", "false").lower() == "true"
    ANALYTICS_RETENTION_DAYS: int = int(os.getenv("ANALYTICS_RETENTION_DAYS", "30"))
    
    @property
    def database_url(self) -> str:
        """Возвращает URL для подключения к базе данных"""
        if self.USE_POSTGRES:
            return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        return "sqlite:///./voting_system.db"
    
    @property
    def redis_url(self) -> str:
        """Возвращает URL для подключения к Redis"""
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
    
    def validate(self) -> bool:
        """Валидация настроек"""
        errors = []
        
        if self.MIN_VOTING_DURATION_MINUTES >= self.MAX_VOTING_DURATION_MINUTES:
            errors.append("MIN_VOTING_DURATION_MINUTES должно быть меньше MAX_VOTING_DURATION_MINUTES")
        
        if self.DEFAULT_VOTING_DURATION_MINUTES < self.MIN_VOTING_DURATION_MINUTES:
            errors.append("DEFAULT_VOTING_DURATION_MINUTES должно быть больше MIN_VOTING_DURATION_MINUTES")
        
        if self.DEFAULT_VOTING_DURATION_MINUTES > self.MAX_VOTING_DURATION_MINUTES:
            errors.append("DEFAULT_VOTING_DURATION_MINUTES должно быть меньше MAX_VOTING_DURATION_MINUTES")
        
        if self.TOKEN_LENGTH < 16:
            errors.append("TOKEN_LENGTH должен быть не менее 16 байт для безопасности")
        
        if self.USE_POSTGRES and not all([self.POSTGRES_HOST, self.POSTGRES_USER, self.POSTGRES_PASSWORD, self.POSTGRES_DB]):
            errors.append("При использовании PostgreSQL необходимо указать все параметры подключения")
        
        if self.USE_REDIS and not self.REDIS_HOST:
            errors.append("При использовании Redis необходимо указать REDIS_HOST")
        
        if self.ENABLE_EMAIL_NOTIFICATIONS and not all([self.SMTP_HOST, self.SMTP_USERNAME, self.SMTP_PASSWORD]):
            errors.append("Для email уведомлений необходимо настроить SMTP параметры")
        
        if self.ENABLE_TELEGRAM_NOTIFICATIONS and not self.TELEGRAM_BOT_TOKEN:
            errors.append("Для Telegram уведомлений необходимо указать TELEGRAM_BOT_TOKEN")
        
        if errors:
            print("❌ Ошибки в конфигурации:")
            for error in errors:
                print(f"  - {error}")
            return False
        
        return True
    
    def print_config(self):
        """Выводит текущую конфигурацию"""
        print("🔧 Текущая конфигурация:")
        print(f"  Host: {self.HOST}")
        print(f"  Port: {self.PORT}")
        print(f"  Debug: {self.DEBUG}")
        print(f"  Use Redis: {self.USE_REDIS}")
        print(f"  Use PostgreSQL: {self.USE_POSTGRES}")
        print(f"  Voting duration: {self.MIN_VOTING_DURATION_MINUTES}-{self.MAX_VOTING_DURATION_MINUTES} min")
        print(f"  Token length: {self.TOKEN_LENGTH} bytes")
        print(f"  Log level: {self.LOG_LEVEL}")

# Создаем глобальный экземпляр настроек
settings = Settings()

# Пример использования переменных окружения
"""
Создайте файл .env со следующим содержимым:

DEBUG=true
SECRET_KEY=your-super-secret-key-here
HOST=0.0.0.0
PORT=8000

# Для использования Redis
USE_REDIS=true
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=your-redis-password

# Для использования PostgreSQL
USE_POSTGRES=true
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=voting_user
POSTGRES_PASSWORD=secure_password
POSTGRES_DB=voting_system

# Для email уведомлений
ENABLE_EMAIL_NOTIFICATIONS=true
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password

# Для Telegram уведомлений
ENABLE_TELEGRAM_NOTIFICATIONS=true
TELEGRAM_BOT_TOKEN=your-bot-token-here
TELEGRAM_CHAT_ID=your-chat-id

# Дополнительные домены для CORS
ADDITIONAL_ORIGINS=https://yourdomain.com,https://www.yourdomain.com

# Аналитика
ENABLE_ANALYTICS=true
ANALYTICS_RETENTION_DAYS=90
"""
