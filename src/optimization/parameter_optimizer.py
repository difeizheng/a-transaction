"""
参数自动优化模块
支持：网格搜索、遗传算法、贝叶斯优化
"""
from typing import Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass, field
from datetime import datetime
import numpy as np
import pandas as pd
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import logging

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ParameterRange:
    """参数范围定义"""
    name: str
    min_val: float
    max_val: float
    step: float = 0.01
    is_int: bool = False

    def get_values(self) -> List:
        """获取所有可能的值"""
        if self.is_int:
            return list(range(int(self.min_val), int(self.max_val) + 1, int(self.step)))
        return np.arange(self.min_val, self.max_val + self.step, self.step).tolist()


@dataclass
class OptimizationResult:
    """优化结果"""
    best_params: Dict
    best_score: float
    total_iterations: int
    optimization_method: str
    all_results: List[Dict] = field(default_factory=list)
    execution_time: float = 0.0

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "best_params": self.best_params,
            "best_score": self.best_score,
            "total_iterations": self.total_iterations,
            "method": self.optimization_method,
            "execution_time": f"{self.execution_time:.2f}s",
        }


class GridSearchOptimizer:
    """
    网格搜索优化器

    优点：简单、可靠、能找到全局最优
    缺点：计算量大、参数多时效率低
    """

    def __init__(
        self,
        parameter_ranges: List[ParameterRange],
        score_function: Callable[[Dict], float],
        n_jobs: int = 1,
    ):
        """
        初始化网格搜索优化器

        Args:
            parameter_ranges: 参数范围列表
            score_function: 评分函数（返回越大越好）
            n_jobs: 并行工作数
        """
        self.parameter_ranges = parameter_ranges
        self.score_function = score_function
        self.n_jobs = n_jobs

    def optimize(self) -> OptimizationResult:
        """执行网格搜索"""
        start_time = datetime.now()

        # 生成所有参数组合
        param_combinations = self._generate_combinations()

        logger.info(f"开始网格搜索，共 {len(param_combinations)} 种参数组合")

        # 执行搜索
        if self.n_jobs > 1:
            results = self._parallel_search(param_combinations)
        else:
            results = self._sequential_search(param_combinations)

        # 找出最优
        best_result = max(results, key=lambda x: x["score"])

        execution_time = (datetime.now() - start_time).total_seconds()

        return OptimizationResult(
            best_params=best_result["params"],
            best_score=best_result["score"],
            total_iterations=len(results),
            optimization_method="grid_search",
            all_results=results,
            execution_time=execution_time,
        )

    def _generate_combinations(self) -> List[Dict]:
        """生成所有参数组合"""
        import itertools

        param_values = [pr.get_values() for pr in self.parameter_ranges]
        param_names = [pr.name for pr in self.parameter_ranges]

        combinations = []
        for values in itertools.product(*param_values):
            combinations.append(dict(zip(param_names, values)))

        return combinations

    def _sequential_search(self, combinations: List[Dict]) -> List[Dict]:
        """顺序搜索"""
        results = []

        for i, params in enumerate(combinations):
            try:
                score = self.score_function(params)
                results.append({
                    "params": params,
                    "score": score,
                    "iteration": i + 1,
                })

                if (i + 1) % 10 == 0:
                    logger.info(f"进度：{i + 1}/{len(combinations)}")

            except Exception as e:
                logger.warning(f"参数 {params} 评估失败：{e}")
                results.append({
                    "params": params,
                    "score": float("-inf"),
                    "iteration": i + 1,
                })

        return results

    def _parallel_search(self, combinations: List[Dict]) -> List[Dict]:
        """并行搜索"""
        results = []

        with ThreadPoolExecutor(max_workers=self.n_jobs) as executor:
            futures = {
                executor.submit(self.score_function, params): i
                for i, params in enumerate(combinations)
            }

            for i, future in enumerate(futures):
                try:
                    score = future.result()
                    results.append({
                        "params": combinations[i],
                        "score": score,
                        "iteration": i + 1,
                    })
                except Exception as e:
                    logger.warning(f"参数评估失败：{e}")
                    results.append({
                        "params": combinations[i],
                        "score": float("-inf"),
                        "iteration": i + 1,
                    })

        return results


class GeneticOptimizer:
    """
    遗传算法优化器

    优点：适合高维参数空间、效率高
    缺点：可能陷入局部最优
    """

    def __init__(
        self,
        parameter_ranges: List[ParameterRange],
        score_function: Callable[[Dict], float],
        population_size: int = 50,
        generations: int = 100,
        crossover_rate: float = 0.8,
        mutation_rate: float = 0.1,
        elite_ratio: float = 0.1,
    ):
        """
        初始化遗传算法优化器

        Args:
            parameter_ranges: 参数范围列表
            score_function: 评分函数
            population_size: 种群大小
            generations: 迭代代数
            crossover_rate: 交叉概率
            mutation_rate: 变异概率
            elite_ratio: 精英比例
        """
        self.parameter_ranges = parameter_ranges
        self.score_function = score_function
        self.population_size = population_size
        self.generations = generations
        self.crossover_rate = crossover_rate
        self.mutation_rate = mutation_rate
        self.elite_ratio = elite_ratio

        self.param_names = [pr.name for pr in parameter_ranges]
        self.param_dict = {pr.name: pr for pr in parameter_ranges}

    def optimize(self) -> OptimizationResult:
        """执行遗传算法优化"""
        start_time = datetime.now()

        # 初始化种群
        population = self._initialize_population()

        all_results = []
        best_individual = None
        best_score = float("-inf")

        for gen in range(self.generations):
            # 评估种群
            scores = []
            for individual in population:
                try:
                    score = self.score_function(individual)
                except Exception as e:
                    score = float("-inf")
                scores.append(score)

                if score > best_score:
                    best_score = score
                    best_individual = individual.copy()

            # 记录结果
            all_results.append({
                "generation": gen,
                "best_score": max(scores),
                "avg_score": np.mean(scores),
            })

            # 选择精英
            elite_count = int(self.population_size * self.elite_ratio)
            elite_indices = np.argsort(scores)[-elite_count:]
            new_population = [population[i].copy() for i in elite_indices]

            # 生成新个体
            while len(new_population) < self.population_size:
                # 选择
                parent1 = self._tournament_selection(population, scores)
                parent2 = self._tournament_selection(population, scores)

                # 交叉
                if np.random.random() < self.crossover_rate:
                    child1, child2 = self._crossover(parent1, parent2)
                else:
                    child1, child2 = parent1.copy(), parent2.copy()

                # 变异
                child1 = self._mutate(child1)
                child2 = self._mutate(child2)

                new_population.append(child1)
                if len(new_population) < self.population_size:
                    new_population.append(child2)

            population = new_population[:self.population_size]

            if gen % 10 == 0:
                logger.info(f"世代 {gen}: 最佳适应度 = {max(scores):.4f}")

        execution_time = (datetime.now() - start_time).total_seconds()

        # 转换为完整参数字典
        best_params = {}
        for name in self.param_names:
            pr = self.param_dict[name]
            val = best_individual.get(name, (pr.min_val + pr.max_val) / 2)
            if pr.is_int:
                best_params[name] = int(round(val))
            else:
                best_params[name] = round(val, 4)

        return OptimizationResult(
            best_params=best_params,
            best_score=best_score,
            total_iterations=self.generations * self.population_size,
            optimization_method="genetic_algorithm",
            all_results=all_results,
            execution_time=execution_time,
        )

    def _initialize_population(self) -> List[Dict]:
        """初始化种群"""
        population = []
        for _ in range(self.population_size):
            individual = {}
            for pr in self.parameter_ranges:
                if pr.is_int:
                    individual[pr.name] = np.random.randint(
                        int(pr.min_val), int(pr.max_val) + 1
                    )
                else:
                    individual[pr.name] = np.random.uniform(pr.min_val, pr.max_val)
            population.append(individual)
        return population

    def _tournament_selection(
        self,
        population: List[Dict],
        scores: List[float],
        tournament_size: int = 5,
    ) -> Dict:
        """锦标赛选择"""
        indices = np.random.choice(len(population), tournament_size, replace=False)
        best_idx = indices[np.argmax([scores[i] for i in indices])]
        return population[best_idx].copy()

    def _crossover(
        self,
        parent1: Dict,
        parent2: Dict,
    ) -> Tuple[Dict, Dict]:
        """算术交叉"""
        alpha = np.random.uniform(0.2, 0.8)

        child1 = {}
        child2 = {}

        for name in self.param_names:
            p1_val = parent1[name]
            p2_val = parent2[name]

            child1[name] = alpha * p1_val + (1 - alpha) * p2_val
            child2[name] = (1 - alpha) * p1_val + alpha * p2_val

        return child1, child2

    def _mutate(self, individual: Dict) -> Dict:
        """高斯变异"""
        mutated = individual.copy()

        for name in self.param_names:
            if np.random.random() < self.mutation_rate:
                pr = self.param_dict[name]
                current_val = mutated[name]
                range_size = pr.max_val - pr.min_val

                # 高斯变异
                mutation = np.random.normal(0, range_size * 0.1)
                new_val = current_val + mutation

                # 限制在范围内
                new_val = max(pr.min_val, min(pr.max_val, new_val))
                mutated[name] = new_val

        return mutated


class StrategyParameterOptimizer:
    """
    策略参数优化器

    封装网格搜索和遗传算法，提供统一的接口
    """

    def __init__(
        self,
        strategy_class,
        price_data: Dict[str, pd.DataFrame],
        initial_capital: float = 100000,
    ):
        """
        初始化策略参数优化器

        Args:
            strategy_class: 策略类
            price_data: 价格数据字典
            initial_capital: 初始资金
        """
        self.strategy_class = strategy_class
        self.price_data = price_data
        self.initial_capital = initial_capital

    def create_default_ranges(self) -> List[ParameterRange]:
        """创建默认参数范围"""
        return [
            ParameterRange("buy_threshold", 0.3, 0.7, 0.05),
            ParameterRange("sell_threshold", 0.2, 0.6, 0.05),
            ParameterRange("atr_multiplier", 1.0, 3.0, 0.25),
            ParameterRange("profit_ratio", 1.5, 4.0, 0.25),
            ParameterRange("adx_threshold", 20, 50, 5, is_int=True),
            ParameterRange("min_buy_conditions", 2, 6, 1, is_int=True),
        ]

    def optimize_grid(
        self,
        parameter_ranges: Optional[List[ParameterRange]] = None,
        n_jobs: int = 4,
    ) -> OptimizationResult:
        """网格搜索优化"""
        if parameter_ranges is None:
            parameter_ranges = self.create_default_ranges()

        optimizer = GridSearchOptimizer(
            parameter_ranges=parameter_ranges,
            score_function=self._evaluate_params,
            n_jobs=n_jobs,
        )

        return optimizer.optimize()

    def optimize_genetic(
        self,
        parameter_ranges: Optional[List[ParameterRange]] = None,
        population_size: int = 30,
        generations: int = 50,
    ) -> OptimizationResult:
        """遗传算法优化"""
        if parameter_ranges is None:
            parameter_ranges = self.create_default_ranges()

        optimizer = GeneticOptimizer(
            parameter_ranges=parameter_ranges,
            score_function=self._evaluate_params,
            population_size=population_size,
            generations=generations,
        )

        return optimizer.optimize()

    def _evaluate_params(self, params: Dict) -> float:
        """
        评估参数组合

        返回：综合评分（考虑收益率、夏普比率、最大回撤）
        """
        from src.strategy.improved_strategy import ImprovedStrategy
        from src.engine.backtest import BacktestEngine, Trade

        try:
            # 创建策略实例
            strategy = ImprovedStrategy(
                buy_threshold=params.get("buy_threshold", 0.5),
                sell_threshold=params.get("sell_threshold", 0.4),
                atr_multiplier=params.get("atr_multiplier", 2.0),
                profit_ratio=params.get("profit_ratio", 2.5),
                adx_threshold=params.get("adx_threshold", 30),
                min_buy_conditions=params.get("min_buy_conditions", 3),
            )

            # 生成信号
            all_signals = []
            for code, df in self.price_data.items():
                signals = strategy.generate_signals(df, code)
                all_signals.extend(signals)

            if not all_signals:
                return float("-inf")

            # 运行回测
            engine = BacktestEngine(initial_capital=self.initial_capital)
            result = engine.run(
                price_data=self.price_data,
                signals=all_signals,
                decision_engine=None,
            )

            # 综合评分 = 年化收益 + 夏普比率 - 最大回撤惩罚
            score = (
                result.annual_return * 0.4 +
                result.sharpe_ratio * 0.3 -
                result.max_drawdown * 0.3
            )

            return score

        except Exception as e:
            logger.warning(f"参数评估失败：{e}")
            return float("-inf")


def run_parameter_optimization_demo():
    """参数优化演示"""
    from src.collectors.price_collector import PriceCollector
    from src.strategy.improved_strategy import ImprovedStrategy

    print("=" * 60)
    print("策略参数优化演示")
    print("=" * 60)

    # 配置
    STOCK_CODES = ["000001", "600000", "000002"]
    DAYS = 120

    print("\n获取历史数据...")
    collector = PriceCollector()

    price_data = {}
    for code in STOCK_CODES:
        df = collector.get_kline(code, period="daily", limit=DAYS)
        if df is not None and not df.empty:
            price_data[code] = df
            print(f"[OK] {code}: {len(df)} 条数据")

    if not price_data:
        print("[ERR] 无法获取数据")
        return

    # 创建优化器
    optimizer = StrategyParameterOptimizer(
        strategy_class=ImprovedStrategy,
        price_data=price_data,
        initial_capital=100000,
    )

    # 简化参数范围用于演示
    param_ranges = [
        ParameterRange("buy_threshold", 0.4, 0.6, 0.1),
        ParameterRange("sell_threshold", 0.3, 0.5, 0.1),
        ParameterRange("atr_multiplier", 1.5, 2.5, 0.5),
        ParameterRange("adx_threshold", 25, 35, 5, is_int=True),
    ]

    print("\n开始网格搜索优化...")
    print(f"参数范围：{[(p.name, p.min_val, p.max_val) for p in param_ranges]}")

    result = optimizer.optimize_grid(
        parameter_ranges=param_ranges,
        n_jobs=4,
    )

    # 输出结果
    print("\n" + "=" * 60)
    print("优化结果")
    print("=" * 60)
    print(f"优化方法：{result.optimization_method}")
    print(f"执行时间：{result.execution_time:.2f}秒")
    print(f"迭代次数：{result.total_iterations}")
    print(f"\n最优参数:")
    for k, v in result.best_params.items():
        print(f"  {k}: {v}")
    print(f"\n最优评分：{result.best_score:.4f}")

    return result


if __name__ == "__main__":
    run_parameter_optimization_demo()
