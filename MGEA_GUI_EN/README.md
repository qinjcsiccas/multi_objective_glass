# MGEA — Inorganic Glass Multi-Objective Property Screening & Optimization

[中文](#中文) | [English](#english)

---

## 中文

### 简介

基于可解释性机器学习与遗传算法的**无机玻璃多目标性能优化平台**。输入元素组成，即时预测五大关键性能（介电常数、介电损耗、热导率、热膨胀系数、杨氏模量），支持自定义优化方向和权重，运行遗传算法搜索帕累托前沿最优组成。
| 10 GHz 介电常数 ε | 1 GHz 介电损耗 tanδ | 室温热导率 κ | 热膨胀系数 α | 杨氏模量 E |
|---|---|---|---|---|

### 引用
Qin, J. *et al.* Multiobjective optimization of dielectric, thermal, and mechanical properties of inorganic glasses utilizing explainable machine learning and genetic algorithm. *Materials Genome Engineering Advances* (2025). [DOI: 10.1002/mgea.70005](https://doi.org/10.1002/mgea.70005)

### 运行要求

- **R** ≥ 4.0（需安装包：`nnet`, `gbm`, `randomForest`, `genalg`, `jsonlite`）
- **Python** ≥ 3.9（需安装包：`streamlit`, `pandas`, `numpy`, `plotly`）
- Windows / macOS / Linux

### 快速开始

```
双击 start_streamlit.bat（Windows）
或
streamlit run mgea_app.py
```

首次运行会自动安装缺失的 Python 包。R 包如缺失，请在 R 控制台中手动安装：
```r
install.packages(c("nnet","gbm","randomForest","genalg","jsonlite"))
```

### 使用说明

**Tab 1：单点性能预测**
1. 在侧边栏输入各元素摩尔比（O 默认电荷中性自动计算）
2. 点击「预测性能」→ 5 张卡片显示预测均值
3. 结果含归一化组成 + 氧化物形式，可下载历史 CSV

**Tab 2：多目标遗传算法优化**
1. 设定各属性的优化方向（↓/↑）和权重（0 = 不参与）
2. 设置 GA 参数（种群大小、代数、突变率、Bootstrap 采样数）
3. 设定元素搜索范围（min / max，0 = 禁用该元素）
4. 点击「开始多目标优化」→ 帕累托前沿结果表格 + 空间分布图 + 最优候选明细

### 文件结构

```
├── start_streamlit.bat   # Windows 一键启动
├── mgea_app.py           # Streamlit 主程序
├── predict.R             # R 预测服务（后台常驻）
├── ga_optimize.R         # R 遗传算法优化
├── models/               # 5 个已训练模型（.RData, 约 145 MB）
│   ├── ann_permittivity_models.RData    # ANN ×1000
│   ├── ann_loss_models.RData            # ANN ×1000
│   ├── ann_thermalC_models.RData        # ANN ×1000
│   ├── gbdt_expansion_models_1.RData    # GBDT ×1
│   └── rf_modulus_models_1.RData        # RF ×1
└── data/                 # 训练数据（CSV）
```

### 模型信息

| 性能 | 模型 | 数量 | 
|---|---|---|
| 介电常数 ε | 人工神经网络 (nnet) | 1000 bootstrap |
| 介电损耗 tanδ | 人工神经网络 (nnet) | 1000 bootstrap |
| 热导率 κ | 人工神经网络 (nnet) | 1000 bootstrap |
| 热膨胀系数 α | 梯度提升树 (gbm) | 1 |
| 杨氏模量 E | 随机森林 (randomForest) | 1 |

---

## English

### Overview

An **inorganic glass multi-objective performance optimization platform** powered by explainable machine learning and genetic algorithms. Input elemental composition to instantly predict five key properties (permittivity, dielectric loss, thermal conductivity, CTE, Young's modulus), then run GA optimization with customizable targets and weights to discover Pareto-optimal compositions.

### Citation

Qin, J. *et al.* Multiobjective optimization of dielectric, thermal, and mechanical properties of inorganic glasses utilizing explainable machine learning and genetic algorithm. *Materials Genome Engineering Advances* (2025). [DOI: 10.1002/mgea.70005](https://doi.org/10.1002/mgea.70005)

### Requirements

- **R** ≥ 4.0 (packages: `nnet`, `gbm`, `randomForest`, `genalg`, `jsonlite`)
- **Python** ≥ 3.9 (packages: `streamlit`, `pandas`, `numpy`, `plotly`)
- Windows / macOS / Linux

### Quick Start

```
Double-click start_streamlit.bat (Windows)
or
streamlit run mgea_app.py
```

Missing Python packages are auto-installed on first run. For missing R packages:
```r
install.packages(c("nnet","gbm","randomForest","genalg","jsonlite"))
```

### Usage

**Tab 1: Single-Point Prediction**
1. Enter elemental molar ratios in the sidebar (O is auto-calculated via charge neutrality)
2. Click "Predict Properties" → 5 cards display predicted mean values
3. Results include normalized composition + oxide form; history downloadable as CSV

**Tab 2: Multi-Objective GA Optimization**
1. Set optimization direction (↓/↑) and weight (0 = excluded) for each property
2. Configure GA parameters (population size, generations, mutation rate, bootstrap samples)
3. Define element search ranges (min / max, 0 = disabled)
4. Click "Run Multi-Objective Optimization" → Pareto frontier table + spatial distribution plots + best candidates detail

### File Structure

```
├── start_streamlit.bat   # One-click launcher (Windows)
├── mgea_app.py           # Streamlit main application
├── predict.R             # R prediction server (persistent background)
├── ga_optimize.R         # R GA optimization script
├── models/               # 5 trained models (.RData, ~145 MB)
│   ├── ann_permittivity_models.RData    # ANN ×1000
│   ├── ann_loss_models.RData            # ANN ×1000
│   ├── ann_thermalC_models.RData        # ANN ×1000
│   ├── gbdt_expansion_models_1.RData    # GBDT ×1
│   └── rf_modulus_models_1.RData        # RF ×1
└── data/                 # Training datasets (CSV)
```

### Model Details

| Property | Model | Count |
|---|---|---|
| Permittivity ε | Artificial Neural Network (nnet) | 1000 bootstrap |
| Dielectric Loss tanδ | Artificial Neural Network (nnet) | 1000 bootstrap |
| Thermal Conductivity κ | Artificial Neural Network (nnet) | 1000 bootstrap |
| CTE α | Gradient Boosted Trees (gbm) | 1 |
| Young's Modulus E | Random Forest (randomForest) | 1 |

---

© Jincheng Qin. *Materials Genome Engineering Advances* 2025. [DOI: 10.1002/mgea.70005](https://doi.org/10.1002/mgea.70005)
