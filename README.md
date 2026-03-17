# Crypto News Pipeline

Automated crypto news aggregator for Telegram channel.

**Flow:** RSS Sources -> Dedup -> Claude Sonnet 4.6 (score + translate) -> Telegram

## Stack
- Python 3.11 / FastAPI / aiogram 3.x
- PostgreSQL (async via SQLAlchemy)
- Anthropic Claude Sonnet 4.6 (scoring + translation)
- APScheduler (15-min polling)
- Railway (deployment)

## Setup
cp .env.example .env
# Fill in your credentials
pip install -r requirements.txt
alembic upgrade head
python -m app.main

## Environment Variables
See .env.example for full list.

## Architecture
Separate microservice. Does NOT share DB or code with Market Lens bot.
Lives in the same Railway project for billing convenience only.
