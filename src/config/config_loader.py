"""
配置加载器 - 支持分层配置、环境变量、配置验证

用法:
    from src.config.config_loader import load_config, get_config

    # 加载配置（自动检测环境）
    config = load_config()

    # 指定环境
    config = load_config(env='production')

    # 获取配置值
    value = get_config('trading.initial_capital')
"""
import os
import re
import yaml
from pathlib import Path
from typing import Any, Dict, Optional
from loguru import logger


class ConfigLoader:
    """配置加载器"""

    def __init__(self, config_dir: str = 'config'):
        self.config_dir = Path(config_dir)
        self.config: Dict[str, Any] = {}
        self.env: str = 'development'

    def load(self, env: Optional[str] = None) -> Dict[str, Any]:
        """
        加载配置

        参数:
            env: 环境名称 (development/production)，默认从环境变量 ENV 读取

        返回:
            配置字典
        """
        # 确定环境
        if env is None:
            env = os.getenv('ENV', 'development')
        self.env = env

        logger.info(f"加载配置环境: {env}")

        # 1. 加载基础配置
        base_config = self._load_yaml('base.yaml')

        # 2. 加载环境配置
        env_config = self._load_yaml(f'{env}.yaml')

        # 3. 合并配置
        self.config = self._merge_config(base_config, env_config)

        # 4. 替换环境变量
        self.config = self._replace_env_vars(self.config)

        # 5. 验证配置
        self._validate_config()

        logger.info(f"配置加载完成: {len(self.config)} 个顶级配置项")
        return self.config

    def _load_yaml(self, filename: str) -> Dict[str, Any]:
        """加载 YAML 文件"""
        filepath = self.config_dir / filename

        if not filepath.exists():
            logger.warning(f"配置文件不存在: {filepath}")
            return {}

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
            logger.debug(f"加载配置文件: {filepath}")
            return config
        except Exception as e:
            logger.error(f"加载配置文件失败 {filepath}: {e}")
            return {}

    def _merge_config(self, base: Dict, override: Dict) -> Dict:
        """
        深度合并配置

        override 中的值会覆盖 base 中的值
        """
        result = base.copy()

        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                # 递归合并字典
                result[key] = self._merge_config(result[key], value)
            else:
                # 直接覆盖
                result[key] = value

        return result

    def _replace_env_vars(self, config: Any) -> Any:
        """
        替换配置中的环境变量

        支持格式: ${VAR_NAME} 或 ${VAR_NAME:default_value}
        """
        if isinstance(config, dict):
            return {k: self._replace_env_vars(v) for k, v in config.items()}
        elif isinstance(config, list):
            return [self._replace_env_vars(item) for item in config]
        elif isinstance(config, str):
            # 匹配 ${VAR_NAME} 或 ${VAR_NAME:default}
            pattern = r'\$\{([^}:]+)(?::([^}]*))?\}'
            matches = re.findall(pattern, config)

            if matches:
                result = config
                for var_name, default_value in matches:
                    env_value = os.getenv(var_name, default_value)
                    result = result.replace(f'${{{var_name}}}', env_value)
                    if default_value:
                        result = result.replace(f'${{{var_name}:{default_value}}}', env_value)
                return result

        return config

    def _validate_config(self):
        """验证配置"""
        # 检查必需的顶级配置项
        required_keys = ['system', 'data_sources', 'trading', 'stock_pool', 'monitor', 'notification']
        missing_keys = [key for key in required_keys if key not in self.config]

        if missing_keys:
            raise ValueError(f"配置缺少必需项: {missing_keys}")

        # 检查交易配置
        trading = self.config.get('trading', {})
        if trading.get('initial_capital', 0) < 1000:
            raise ValueError("initial_capital 必须 >= 1000")

        if not (0.1 <= trading.get('max_position_per_stock', 0) <= 1.0):
            raise ValueError("max_position_per_stock 必须在 0.1-1.0 之间")

        # 检查股票池配置
        stock_pool = self.config.get('stock_pool', {})
        if stock_pool.get('type') == 'custom':
            codes = stock_pool.get('custom_codes', [])
            if not codes:
                raise ValueError("custom 模式下 custom_codes 不能为空")

            # 验证股票代码格式
            for code in codes:
                if not re.match(r'^[0-9]{6}$', code):
                    raise ValueError(f"无效的股票代码: {code}")

        logger.info("配置验证通过")

    def get(self, key_path: str, default: Any = None) -> Any:
        """
        获取配置值

        参数:
            key_path: 配置路径，用点分隔，如 'trading.initial_capital'
            default: 默认值

        返回:
            配置值
        """
        keys = key_path.split('.')
        value = self.config

        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default

        return value

    def set(self, key_path: str, value: Any):
        """
        设置配置值（运行时修改）

        参数:
            key_path: 配置路径，用点分隔
            value: 配置值
        """
        keys = key_path.split('.')
        config = self.config

        for key in keys[:-1]:
            if key not in config:
                config[key] = {}
            config = config[key]

        config[keys[-1]] = value
        logger.debug(f"设置配置: {key_path} = {value}")


# 全局配置加载器实例
_config_loader: Optional[ConfigLoader] = None


def load_config(env: Optional[str] = None, config_dir: str = 'config') -> Dict[str, Any]:
    """
    加载配置

    参数:
        env: 环境名称 (development/production)
        config_dir: 配置目录

    返回:
        配置字典
    """
    global _config_loader

    _config_loader = ConfigLoader(config_dir)
    return _config_loader.load(env)


def get_config(key_path: str = None, default: Any = None) -> Any:
    """
    获取配置值

    参数:
        key_path: 配置路径，如 'trading.initial_capital'，为 None 时返回全部配置
        default: 默认值

    返回:
        配置值
    """
    if _config_loader is None:
        raise RuntimeError("配置未加载，请先调用 load_config()")

    if key_path is None:
        return _config_loader.config

    return _config_loader.get(key_path, default)


def set_config(key_path: str, value: Any):
    """
    设置配置值（运行时修改）

    参数:
        key_path: 配置路径
        value: 配置值
    """
    if _config_loader is None:
        raise RuntimeError("配置未加载，请先调用 load_config()")

    _config_loader.set(key_path, value)


def get_env() -> str:
    """获取当前环境"""
    if _config_loader is None:
        return os.getenv('ENV', 'development')
    return _config_loader.env


if __name__ == '__main__':
    # 测试配置加载
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    # 测试开发环境
    print("=" * 60)
    print("测试开发环境配置")
    print("=" * 60)
    config = load_config('development')
    print(f"环境: {get_env()}")
    print(f"日志级别: {get_config('system.log_level')}")
    print(f"初始资金: {get_config('trading.initial_capital')}")
    print(f"监控间隔: {get_config('monitor.interval')}")
    print(f"股票池: {get_config('stock_pool.custom_codes')}")

    # 测试生产环境
    print("\n" + "=" * 60)
    print("测试生产环境配置")
    print("=" * 60)
    config = load_config('production')
    print(f"环境: {get_env()}")
    print(f"日志级别: {get_config('system.log_level')}")
    print(f"初始资金: {get_config('trading.initial_capital')}")
    print(f"监控间隔: {get_config('monitor.interval')}")
    print(f"股票池: {get_config('stock_pool.custom_codes')}")
