from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """统一的 SQLAlchemy 元数据基类，后续业务模型会在此基础上注册。"""
