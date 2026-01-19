#!/bin/bash
# QuizBot Production Deployment Script
# Run on AWS Ubuntu server: bash deploy.sh

set -e  # Exit on error

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PROJECT_DIR="/home/ubuntu/QuizBot"
DOMAIN="xamidullayevi.uz"

echo -e "${GREEN}=== QuizBot Production Deployment ===${NC}"
echo ""

# Step 1: Pre-flight checks
echo -e "${YELLOW}[1/7] Pre-flight checks...${NC}"
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Docker not installed. Installing...${NC}"
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker $USER
    echo -e "${YELLOW}Please log out and back in, then re-run this script.${NC}"
    exit 1
fi

if ! command -v nginx &> /dev/null; then
    echo -e "${RED}Nginx not installed. Installing...${NC}"
    sudo apt update && sudo apt install -y nginx certbot python3-certbot-nginx
fi

# Step 2: Backup current state
echo -e "${YELLOW}[2/7] Creating backup...${NC}"
cd "$PROJECT_DIR"
BACKUP_NAME="backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p backups
if [ -f .env ]; then
    cp .env "backups/${BACKUP_NAME}.env"
fi
sudo docker exec quizbot_db pg_dump -U postgres quizbot > "backups/${BACKUP_NAME}.sql" 2>/dev/null || echo "DB backup skipped (container not running)"
echo -e "${GREEN}Backup created: backups/${BACKUP_NAME}${NC}"

# Step 3: Pull latest code
echo -e "${YELLOW}[3/7] Pulling latest code...${NC}"
git stash
git pull origin main
git stash pop 2>/dev/null || true

# Step 4: Validate .env
echo -e "${YELLOW}[4/7] Checking .env configuration...${NC}"
if [ ! -f .env ]; then
    echo -e "${RED}.env file not found! Copy from .env.example and configure.${NC}"
    exit 1
fi

if ! grep -q "WEBAPP_URL=https://" .env; then
    echo -e "${RED}WEBAPP_URL not set! Add: WEBAPP_URL=https://${DOMAIN}${NC}"
    exit 1
fi

echo -e "${GREEN}.env looks good.${NC}"

# Step 5: Rebuild containers
echo -e "${YELLOW}[5/7] Rebuilding Docker containers...${NC}"
sudo docker compose down
sudo docker compose up -d --build

# Wait for healthy
echo "Waiting for containers to be healthy..."
sleep 10
sudo docker compose ps

# Step 6: Health check
echo -e "${YELLOW}[6/7] Running health checks...${NC}"

# Check API is responding
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/api/quizzes || echo "000")
if [ "$HTTP_CODE" == "401" ]; then
    echo -e "${GREEN}API responding (401 = auth required - correct!)${NC}"
elif [ "$HTTP_CODE" == "200" ]; then
    echo -e "${GREEN}API responding (200 OK)${NC}"
else
    echo -e "${RED}API not responding. Check logs: sudo docker logs quizbot_app${NC}"
fi

# Check Nginx
if sudo nginx -t 2>/dev/null; then
    echo -e "${GREEN}Nginx config OK${NC}"
else
    echo -e "${RED}Nginx config error. Run: sudo nginx -t${NC}"
fi

# Step 7: Summary
echo ""
echo -e "${GREEN}=== Deployment Complete ===${NC}"
echo ""
echo "Next steps:"
echo "1. If SSL not yet configured: sudo certbot --nginx -d ${DOMAIN} -d www.${DOMAIN}"
echo "2. Test: curl -I https://${DOMAIN}"
echo "3. Check logs: sudo docker logs quizbot_app -f --tail 50"
echo ""
echo -e "${YELLOW}🔴 REMINDER: If tokens were exposed, rotate them via BotFather and Groq dashboard!${NC}"
