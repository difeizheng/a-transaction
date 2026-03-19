"""
日志模块 - 系统日志配置
"""
import sys
from pathlib import Path
from loguru import logger


def setup_logger(
    log_dir: str = "logs",
    log_level: str = "INFO",
    rotation: str = "1 day",
    retention: str = "30 days",
) -> None:
    """
    配置系统日志

    Args:
        log_dir: 日志目录
        log_level: 日志级别 (DEBUG/INFO/WARNING/ERROR/CRITICAL)
        rotation: 日志轮转策略
        retention: 日志保留时间
    """
    # 移除默认的处理器
    logger.remove()

    # 创建日志目录
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # 控制台输出格式（彩色）
    console_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    # 文件格式（详细）
    file_format = (
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
        "{level: <8} | "
        "{name}:{function}:{line} | "
        "{message}"
    )

    # 添加控制台处理器
    logger.add(
        sys.stderr,
        format=console_format,
        level=log_level,
        colorize=True,
    )

    # 添加通用日志文件处理器
    logger.add(
        log_path / "app_{time:YYYY-MM-DD}.log",
        format=file_format,
        level=log_level,
        rotation=rotation,
        retention=retention,
        encoding="utf-8",
    )

    # 添加错误日志文件处理器
    logger.add(
        log_path / "error_{time:YYYY-MM-DD}.log",
        format=file_format,
        level="ERROR",
        rotation=rotation,
        retention=retention,
        encoding="utf-8",
    )

    # 添加交易日志文件处理器
    logger.add(
        log_path / "trading_{time:YYYY-MM-DD}.log",
        format=file_format,
        level="INFO",
        rotation=rotation,
        retention=retention,
        encoding="utf-8",
    )


def get_logger(name: str = None):
    """
    获取日志记录器

    Args:
        name: 日志记录器名称（通常是模块名）

    Returns:
        logger 实例
    """
    if name:
        return logger.bind(name=name)
    return logger


# 重新导出 logger
__all__ = ["setup_logger", "get_logger", "logger"]
