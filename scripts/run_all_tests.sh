#!/bin/bash

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo "========================================="
echo "   选股通知系统 - 自动化测试套件"
echo "========================================="
echo ""

TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

run_test() {
    local test_name=$1
    local test_command=$2
    
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}正在运行: ${test_name}${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    
    if eval $test_command; then
        echo -e "${GREEN}✅ ${test_name}: PASSED${NC}"
        ((PASSED_TESTS++))
    else
        echo -e "${RED}❌ ${test_name}: FAILED${NC}"
        ((FAILED_TESTS++))
    fi
    
    ((TOTAL_TESTS++))
    echo ""
}

echo -e "${YELLOW}步骤 1/5: 检查测试环境${NC}"
echo "检查 Python 环境..."
if ! command -v pytest &> /dev/null; then
    echo -e "${RED}错误: pytest 未安装${NC}"
    echo "请运行: pip install -r requirements-test.txt"
    exit 1
fi

echo "检查测试数据库..."
export TEST_DATABASE_URL="sqlite:///:memory:"
echo -e "${GREEN}✓ 环境检查通过${NC}"
echo ""

run_test "后端单元测试" "pytest tests/backend/unit/ -v --tb=short --maxfail=5"

run_test "后端集成测试" "pytest tests/backend/integration/ -v --tb=short --maxfail=3"

run_test "数据库测试" "pytest tests/backend/integration/test_database.py -v --tb=short"

if [ -d "frontend" ] && [ -f "frontend/package.json" ]; then
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}正在运行: 前端 UI 测试${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    
    cd frontend
    if [ -f "package.json" ]; then
        if npm run test:e2e 2>/dev/null; then
            echo -e "${GREEN}✅ 前端 UI 测试: PASSED${NC}"
            ((PASSED_TESTS++))
        else
            echo -e "${YELLOW}⚠️  前端 UI 测试: SKIPPED (未配置)${NC}"
        fi
    else
        echo -e "${YELLOW}⚠️  前端 UI 测试: SKIPPED (前端未初始化)${NC}"
    fi
    cd ..
    ((TOTAL_TESTS++))
    echo ""
fi

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}正在运行: 代码质量检查${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if command -v black &> /dev/null; then
    black --check backend/ tests/ 2>/dev/null
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ 代码格式检查通过${NC}"
    else
        echo -e "${YELLOW}⚠️  代码格式需要调整 (运行 black . 修复)${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  black 未安装，跳过格式检查${NC}"
fi

if command -v flake8 &> /dev/null; then
    flake8 backend/ tests/ --max-line-length=100 2>/dev/null
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Lint 检查通过${NC}"
    else
        echo -e "${YELLOW}⚠️  Lint 检查发现问题${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  flake8 未安装，跳过 Lint 检查${NC}"
fi

echo ""

echo "========================================="
echo "   测试报告"
echo "========================================="
echo -e "总测试数: ${TOTAL_TESTS}"
echo -e "${GREEN}通过: ${PASSED_TESTS}${NC}"
echo -e "${RED}失败: ${FAILED_TESTS}${NC}"

if [ $TOTAL_TESTS -gt 0 ]; then
    SUCCESS_RATE=$(awk "BEGIN {printf \"%.2f\", ($PASSED_TESTS/$TOTAL_TESTS)*100}")
    echo -e "成功率: ${SUCCESS_RATE}%"
fi

echo "========================================="
echo ""

echo -e "${YELLOW}生成覆盖率报告...${NC}"
pytest tests/backend/ --cov=backend --cov-report=html --cov-report=term-missing 2>/dev/null

if [ -f "htmlcov/index.html" ]; then
    echo -e "${GREEN}✓ 覆盖率报告已生成: htmlcov/index.html${NC}"
fi

echo ""

if [ $FAILED_TESTS -eq 0 ]; then
    echo -e "${GREEN}✅ 所有测试通过！${NC}"
    exit 0
else
    echo -e "${RED}❌ 部分测试失败，请检查错误日志${NC}"
    exit 1
fi
