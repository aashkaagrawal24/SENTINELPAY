from sqlalchemy import create_engine, text


def test_repository_db_smoke():
    with create_engine("sqlite://").connect() as connection:
        assert connection.execute(text("select 1")).scalar_one() == 1
