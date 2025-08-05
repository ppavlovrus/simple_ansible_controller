import os
from typing import Optional


class Config:
    """Application configuration"""
    
    # LLM Configuration
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai")
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    ANTHROPIC_API_KEY: Optional[str] = os.getenv("ANTHROPIC_API_KEY")
    
    # Database Configuration
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://user123:password@db:5432/tasksdb")
    
    # Redis Configuration
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    
    # Application Configuration
    DEBUG: bool = os.getenv("DEBUG", "True").lower() == "true"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    # LLM Model Configuration
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4")
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-3-sonnet-20240229")
    
    # Safety Configuration
    DEFAULT_SAFETY_LEVEL: str = os.getenv("DEFAULT_SAFETY_LEVEL", "medium")
    MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "2000"))
    TEMPERATURE: float = float(os.getenv("TEMPERATURE", "0.3"))
    
    @classmethod
    def validate(cls) -> list:
        """Validate configuration and return list of errors"""
        errors = []
        
        if cls.LLM_PROVIDER == "openai" and not cls.OPENAI_API_KEY:
            errors.append("OPENAI_API_KEY is required when LLM_PROVIDER is 'openai'")
        
        if cls.LLM_PROVIDER == "anthropic" and not cls.ANTHROPIC_API_KEY:
            errors.append("ANTHROPIC_API_KEY is required when LLM_PROVIDER is 'anthropic'")
        
        if cls.LLM_PROVIDER not in ["openai", "anthropic"]:
            errors.append(f"Unsupported LLM_PROVIDER: {cls.LLM_PROVIDER}")
        
        return errors
    
    @classmethod
    def get_llm_config(cls) -> dict:
        """Get LLM-specific configuration"""
        return {
            "provider": cls.LLM_PROVIDER,
            "model": cls.OPENAI_MODEL if cls.LLM_PROVIDER == "openai" else cls.ANTHROPIC_MODEL,
            "max_tokens": cls.MAX_TOKENS,
            "temperature": cls.TEMPERATURE,
            "api_key": cls.OPENAI_API_KEY if cls.LLM_PROVIDER == "openai" else cls.ANTHROPIC_API_KEY
        } 