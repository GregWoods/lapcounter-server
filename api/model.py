from typing import Optional
from sqlmodel import Field, Session, SQLModel, create_engine, select



class car_manufacturers(SQLModel, table=True):
    #https://sqlmodel.tiangolo.com/tutorial/automatic-id-none-refresh/
    id: int | None = Field(default=None, primary_key=True)
    name: str


class car_categories(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)


class car_models(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    car_category_id: int | None = Field(default=None, foreign_key="car_categories.id")
    manufacturer_id: int | None = Field(default=None, foreign_key="car_manufacturers.id")
    name: str
    race_number: str
    model_number: str

# not using relationships yet
#  https://sqlmodel.tiangolo.com/tutorial/relationship-attributes/define-relationships-attributes/#declare-relationship-attributes




sqlite_file_name = "database.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"

engine = create_engine(sqlite_url, echo=True)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


if __name__ == "__main__":
    create_db_and_tables()
