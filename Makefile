.PHONY: up down test lint migrate makemigrations shell logs seed benchmark

up:
	docker-compose up -d --build

down:
	docker-compose down

test:
	docker-compose exec web pytest src/ -v

lint:
	docker-compose exec web ruff check src/
	docker-compose exec web mypy src/

migrate:
	docker-compose exec web python src/manage.py migrate

makemigrations:
	docker-compose exec web python src/manage.py makemigrations

shell:
	docker-compose exec web python src/manage.py shell

logs:
	docker-compose logs -f

seed:
	docker-compose exec web python src/scripts/seed_data.py

benchmark:
	docker-compose exec web python src/scripts/seed_data.py
	docker-compose exec web pytest src/ -k benchmark -v
