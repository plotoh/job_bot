from asyncpg import Pool


# ===== Инициализация таблиц =====
async def init_tables(pool: Pool):
    """Создаёт таблицы, если их нет."""
    async with pool.acquire() as conn:
        # Таблица вакансий
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS vacancies (
                id SERIAL PRIMARY KEY,
                vacancy_id VARCHAR(255) UNIQUE NOT NULL,
                vacancy_text TEXT,
                check_word VARCHAR(255),
                has_cover BOOLEAN DEFAULT FALSE,
                has_response BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        ''')
        # Таблица откликов
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS responses (
                id SERIAL PRIMARY KEY,
                vacancy_id INTEGER REFERENCES vacancies(id) ON DELETE CASCADE,
                cover_letter TEXT,
                status VARCHAR(50) DEFAULT 'pending',  -- pending, sent, error
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        ''')


# ===== CRUD для вакансий =====
async def add_vacancy(pool: Pool, vacancy_id: str, vacancy_text: str, check_word: str = None):
    """Добавляет новую вакансию, если её ещё нет. Возвращает id записи."""
    async with pool.acquire() as conn:
        result = await conn.fetchrow('''
            INSERT INTO vacancies (vacancy_id, vacancy_text, check_word)
            VALUES ($1, $2, $3)
            ON CONFLICT (vacancy_id) DO NOTHING
            RETURNING id
        ''', vacancy_id, vacancy_text, check_word)
        return result['id'] if result else None


async def get_vacancies_without_response(pool: Pool):
    """Возвращает список вакансий, на которые ещё не было отклика."""
    async with pool.acquire() as conn:
        rows = await conn.fetch('''
            SELECT * FROM vacancies
            WHERE has_response = FALSE
            ORDER BY created_at DESC
        ''')
        return [dict(row) for row in rows]


async def update_vacancy_response(pool: Pool, vacancy_db_id: int):
    """Отмечает вакансию как имеющую отклик (has_response = TRUE)."""
    async with pool.acquire() as conn:
        await conn.execute('''
            UPDATE vacancies SET has_response = TRUE
            WHERE id = $1
        ''', vacancy_db_id)


# ===== CRUD для откликов =====
async def add_response(pool: Pool, vacancy_db_id: int, cover_letter: str, status: str = 'pending'):
    """Добавляет запись об отклике и связывает с вакансией."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Вставляем отклик
            response_id = await conn.fetchval('''
                INSERT INTO responses (vacancy_id, cover_letter, status)
                VALUES ($1, $2, $3)
                RETURNING id
            ''', vacancy_db_id, cover_letter, status)
            # Обновляем флаг у вакансии
            await conn.execute('''
                UPDATE vacancies SET has_response = TRUE
                WHERE id = $1
            ''', vacancy_db_id)
            return response_id


async def get_responses_by_status(pool: Pool, status: str = 'pending'):
    """Получить все отклики с определённым статусом."""
    async with pool.acquire() as conn:
        rows = await conn.fetch('''
            SELECT * FROM responses
            WHERE status = $1
            ORDER BY created_at DESC
        ''', status)
        return [dict(row) for row in rows]


async def update_response_status(pool: Pool, response_id: int, new_status: str):
    """Обновить статус отклика."""
    async with pool.acquire() as conn:
        await conn.execute('''
            UPDATE responses SET status = $1
            WHERE id = $2
        ''', new_status, response_id)
