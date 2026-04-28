#!/bin/bash

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo "========================================="
echo "   本地测试执行（不使用 Docker）"
echo "========================================="
echo ""

echo -e "${YELLOW}步骤 1/3: 设置测试环境${NC}"
export TESTING=true
export DATABASE_URL="sqlite:///:memory:"
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
echo -e "${GREEN}✓ 环境变量已设置${NC}"
echo ""

echo -e "${YELLOW}步骤 2/3: 检查测试依赖${NC}"
if [ ! -f ".venv/bin/pytest" ]; then
    echo -e "${RED}错误: pytest 未安装${NC}"
    echo "请运行: .venv/bin/pip install -r requirements-test.txt"
    exit 1
fi
echo -e "${GREEN}✓ pytest 已安装${NC}"
echo ""

echo -e "${YELLOW}步骤 3/3: 执行测试${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

.venv/bin/pytest tests/backend/ -v --cov=backend --cov-report=html --cov-report=term-missing

TEST_EXIT_CODE=$?

echo ""
echo "========================================="
echo "   测试报告"
echo "========================================="

if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✅ 所有测试通过！${NC}"
    echo ""
    echo -e "${BLUE}📊 覆盖率报告已生成: htmlcov/index.html${NC}"
    echo ""
    exit 0
else
    echo -e "${RED}❌ 部分测试失败，请检查错误日志${NC}"
    echo ""
    exit 1
fi
