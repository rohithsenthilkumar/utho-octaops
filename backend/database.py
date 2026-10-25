"""
SmartCloud Optimizer — SQLite Database Configuration
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'smartcloud.db')}")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI Dependency for database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def upgrade_db_schema():
    """Safely migrate SQLite database schema for Stage 6 multi-tenancy without data loss."""
    if DATABASE_URL.startswith("sqlite"):
        try:
            with engine.connect() as conn:
                cursor = conn.connection.cursor()
                cursor.execute("PRAGMA table_info(cloud_resources)")
                existing_cols = [row[1] for row in cursor.fetchall()]
                if existing_cols:
                    if "tenant_id" not in existing_cols:
                        cursor.execute("ALTER TABLE cloud_resources ADD COLUMN tenant_id VARCHAR DEFAULT 'tenant-cloudflow'")
                    if "owner_id" not in existing_cols:
                        cursor.execute("ALTER TABLE cloud_resources ADD COLUMN owner_id VARCHAR")
                    if "can_scale_horizontally" not in existing_cols:
                        cursor.execute("ALTER TABLE cloud_resources ADD COLUMN can_scale_horizontally BOOLEAN DEFAULT 0")

                cursor.execute("PRAGMA table_info(resource_policies)")
                policy_cols = [row[1] for row in cursor.fetchall()]
                if policy_cols:
                    if "allow_auto_scaling" not in policy_cols:
                        cursor.execute("ALTER TABLE resource_policies ADD COLUMN allow_auto_scaling BOOLEAN DEFAULT 1")
                    if "min_replicas" not in policy_cols:
                        cursor.execute("ALTER TABLE resource_policies ADD COLUMN min_replicas INTEGER DEFAULT 1")
                    if "max_replicas" not in policy_cols:
                        cursor.execute("ALTER TABLE resource_policies ADD COLUMN max_replicas INTEGER DEFAULT 5")
                    if "can_scale_horizontally" not in policy_cols:
                        cursor.execute("ALTER TABLE resource_policies ADD COLUMN can_scale_horizontally BOOLEAN DEFAULT 0")
                conn.connection.commit()
        except Exception as e:
            print(f"Schema upgrade notice: {e}")


def init_db():
    """Create all tables and run schema upgrades."""
    Base.metadata.create_all(bind=engine)
    upgrade_db_schema()

