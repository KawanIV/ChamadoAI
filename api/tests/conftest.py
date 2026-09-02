import os, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("JWT_SECRET","test-jwt-secret-that-is-at-least-32-characters")
os.environ.setdefault("PUBLIC_LINK_SECRET","test-public-secret-that-is-at-least-32-chars")
os.environ.setdefault("AI_CREDENTIALS_KEY","test-ai-credentials-key-that-is-at-least-32-characters")
os.environ.setdefault("DATABASE_URL","postgresql+asyncpg://x:x@localhost:5432/x")
os.environ.setdefault("ENVIRONMENT","test")
