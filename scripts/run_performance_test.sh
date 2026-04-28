#!/bin/bash

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo "========================================="
echo "   Locust 性能测试 - 选股通知系统"
echo "========================================="

# 检查后端服务是否运行
check_backend() {
    if curl -s http://localhost:9999/api/v1/health > /dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

echo -e "${YELLOW}步骤 1/4: 检查后端服务${NC}"

if check_backend; then
    echo -e "${GREEN}✓ 后端服务已运行 (http://localhost:9999)${NC}"
else
    echo -e "${RED}✗ 后端服务未运行，正在启动...${NC}"
    echo -e "${BLUE}提示: 请在另一个终端运行:${NC}"
    echo "  .venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 9999"
    exit 1
fi

echo ""
echo -e "${YELLOW}步骤 2/4: 检查 Locust 是否安装${NC}"

if .venv/bin/locust --version > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Locust 已安装${NC}"
else
    echo -e "${RED}✗ Locust 未安装${NC}"
    echo "请运行: .venv/bin/pip install locust"
    exit 1
fi

echo ""
echo -e "${YELLOW}步骤 3/4: 创建结果目录${NC}"
mkdir -p performance_results
echo -e "${GREEN}✓ 结果目录已创建${NC}"

echo ""
echo -e "${YELLOW}步骤 4/4: 执行性能测试${NC}"
echo ""

# 基准测试
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}[1/3] 基准测试 (10用户, 60秒)${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

.venv/bin/locust \
    -f tests/performance/locustfile.py \
    --host=http://localhost:9999 \
    --users=10 \
    --spawn-rate=2 \
    --run-time=60s \
    --headless \
    --csv=performance_results/baseline \
    --loglevel INFO

echo ""
echo -e "${BLUE}[2/3] 负载测试 (30用户, 120秒)${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

.venv/bin/locust \
    -f tests/performance/locustfile.py \
    --host=http://localhost:9999 \
    --users=30 \
    --spawn-rate=5 \
    --run-time=120s \
    --headless \
    --csv=performance_results/load_test \
    --loglevel INFO

echo ""
echo -e "${BLUE}[3/3] 压力测试 (50用户, 180秒)${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

.venv/bin/locust \
    -f tests/performance/locustfile.py \
    --host=http://localhost:9999 \
    --users=50 \
    --spawn-rate=10 \
    --run-time=180s \
    --headless \
    --csv=performance_results/stress_test \
    --loglevel INFO

echo ""
echo "========================================="
echo "   性能测试完成"
echo "========================================="
echo ""
echo -e "${GREEN}📊 测试结果文件:${NC}"
ls -lh performance_results/*.csv 2>/dev/null || echo "无结果文件"
echo ""
echo -e "${BLUE}📈 查看详细报告:${NC}"
echo "  baseline_stats.csv      - 基准测试统计"
echo "  load_test_stats.csv     - 负载测试统计"
echo "  stress_test_stats.csv   - 压力测试统计"
echo ""
echo -e "${YELLOW}💡 提示: 使用 Web UI 模式进行交互式测试:${NC}"
echo "  .venv/bin/locust -f tests/performance/locustfile.py --host=http://localhost:9999"
echo ""
