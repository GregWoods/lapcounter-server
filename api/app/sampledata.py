# Running this script will drop all tables and create them again, then add sample data.
# Before running this script, make sure you set the environment variables, or Pydantic validation will fail
# There is a setenv.ps1 file to do this, or running inside the "dev" Docker compose based container will set them for you.

from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional
from sqlmodel import Session, SQLModel, create_engine
from model import (
    CarManufacturer, CarCategory, CarModel, Car,
    CarTyre, ChipHardware, ChipFirmware,
    Driver, Meeting, MeetingDriver, MeetingCar,
    RaceSession, Race, DriverRace, DriverLap,
    Lane
)
from settings import Settings

def add_car_manufacturers(session: Session):
    session.add_all([
        CarManufacturer(id=1, name='Scalextric'),
        CarManufacturer(id=2, name='Policar')
    ])
    session.commit()


def add_car_categories(session: Session):
    session.add_all([
        CarCategory(id=1, name='Porsche'),
        CarCategory(id=2, name='Modern GT'),
        CarCategory(id=3, name='Rally & Rallycross'),
        CarCategory(id=4, name='Modern F1'),
        CarCategory(id=5, name='Other')
    ])
    session.commit()


def add_car_models(session: Session):
    session.add_all([
        CarModel(id=1, car_category_id=1, manufacturer_id=1, name='Porsche 997 Red Teco/Burgfonds', race_number='2', model_number='C2899'),
        CarModel(id=2, car_category_id=1, manufacturer_id=1, name='Porsche 997 Blue Morellato', race_number='17', model_number='C2990'),
        CarModel(id=3, car_category_id=1, manufacturer_id=1, name='Porsche 997 Yellow Forum Gelb', race_number='46', model_number='C2691'),
        CarModel(id=4, car_category_id=1, manufacturer_id=1, name='Porsche 997 Black Mad Butcher', race_number='1', model_number='C3132'),
        CarModel(id=5, car_category_id=1, manufacturer_id=1, name='Porsche 997 Green Street', race_number='', model_number='C3074'),
        CarModel(id=6, car_category_id=1, manufacturer_id=1, name='Porsche 997 Orange Street', race_number='', model_number='C2871'),
        CarModel(id=7, car_category_id=1, manufacturer_id=1, name='Porsche 997 Silver Street', race_number='', model_number='C3021')
    ])
    session.commit()


def add_car_tyres(session: Session):
    session.add_all([
        CarTyre(id=1, brand='Scalextric', compound=' Factory Rubber', size=''),
        CarTyre(id=2, brand='WASP', compound='WASP 04', size=''),
        CarTyre(id=3, brand='Slot.it', compound='P6', size='18x10 Dwg 1207'),
        CarTyre(id=4, brand='PCS', compound='F22 Grey Race Control Tyre', size='18x10')
    ])
    session.commit()


def add_chip_hardwares(session: Session):
    session.add_all([
        ChipHardware(id=1, name='Scalextric C8515 Rev H'),
        ChipHardware(id=2, name='Scalextric C8515 Rev G'),
        ChipHardware(id=3, name='Scalextric C8515 Rev F'),
        ChipHardware(id=4, name='Scalextric C7005')
    ])
    session.commit()


def add_chip_firmwares(session: Session):
    session.add_all([
        ChipFirmware(id=1, name='Scalextric Factory Firmware'),
        ChipFirmware(id=2, name='InCar Pro 3.3'),
        ChipFirmware(id=3, name='InCar Pro 4.0'),
        ChipFirmware(id=4, name='InCar Pro 4.01')
    ])
    session.commit()


def add_cars(session: Session):
    session.add_all([
        Car(id=1, name='Porsche Red/Black', car_model_id=1, tyre_id=1, magnet=False, 
            modifications_notes='', weight_added=20.0, chip_hardware_id=1, chip_firmware_id=1, 
            picture='GT_Porsche_RedBlack.jpg', rfid=''),
        Car(id=2, name='Porsche Red/silver', car_model_id=1, tyre_id=1, magnet=False, 
            modifications_notes='', weight_added=20.0, chip_hardware_id=1, chip_firmware_id=1, 
            picture='GT_Porsche_RedSilver.jpg', rfid=''),
        Car(id=3, name='Porsche Blue/silver', car_model_id=2, tyre_id=1, magnet=False, 
            modifications_notes='', weight_added=20.0, chip_hardware_id=1, chip_firmware_id=1, 
            picture='GT_Porsche_BlueSilver.jpg', rfid=''),
        Car(id=4, name='Porsche Blue/Black', car_model_id=2, tyre_id=1, magnet=False, 
            modifications_notes='Slot.it Starter Kit Sidewinder 36t 17.3x8.25mm Wheels', 
            weight_added=20.0, chip_hardware_id=1, chip_firmware_id=1, 
            picture='GT_Porsche_BlueBlack.jpg', rfid=''),
        Car(id=5, name='Porsche Yellow', car_model_id=3, tyre_id=1, magnet=False, 
            modifications_notes='', weight_added=20.0, chip_hardware_id=1, chip_firmware_id=1, 
            picture='GT_Porsche_Yellow.jpg', rfid=''),
        Car(id=6, name='Porsche Black', car_model_id=4, tyre_id=1, magnet=False, 
            modifications_notes='', weight_added=20.0, chip_hardware_id=1, chip_firmware_id=1, 
            picture='GT_Porsche_Black.jpg', rfid=''),
        Car(id=7, name='Porsche Green', car_model_id=5, tyre_id=1, magnet=False, 
            modifications_notes='', weight_added=20.0, chip_hardware_id=1, chip_firmware_id=1, 
            picture='GT_Porsche_Green.jpg', rfid=''),
        Car(id=8, name='Porsche Orange', car_model_id=6, tyre_id=1, magnet=False, 
            modifications_notes='', weight_added=20.0, chip_hardware_id=1, chip_firmware_id=1, 
            picture='GT_Porsche_Orange.jpg', rfid=''),
        Car(id=9, name='Porsche Silver', car_model_id=7, tyre_id=1, magnet=False, 
            modifications_notes='', weight_added=20.0, chip_hardware_id=1, chip_firmware_id=1, 
            picture='GT_Porsche_Silver.jpg', rfid='')
    ])
    session.commit()


def add_drivers(session: Session):
    session.add_all([
        Driver(id=1, first_name='Driver A', last_name='', mobile_number='', picture='', rfid=''),
        Driver(id=2, first_name='Driver B', last_name='', mobile_number='', picture='', rfid=''),
        Driver(id=3, first_name='Driver C', last_name='', mobile_number='', picture='', rfid=''),
        Driver(id=4, first_name='Driver D', last_name='', mobile_number='', picture='', rfid=''),
        Driver(id=5, first_name='Driver E', last_name='', mobile_number='', picture='', rfid=''),
        Driver(id=6, first_name='Driver F', last_name='', mobile_number='', picture='', rfid=''),
        Driver(id=7, first_name='Driver G', last_name='', mobile_number='', picture='', rfid=''),
        Driver(id=8, first_name='Driver H', last_name='', mobile_number='', picture='', rfid=''),
        Driver(id=9, first_name='Driver J', last_name='', mobile_number='', picture='', rfid='', sit_out_next_race=True)
    ])
    session.commit()


def add_meetings(session: Session):
    session.add_all([
        Meeting(id=1, name='Junior Championship', date=date(2024, 6, 1), venue='Village Hall'),
        Meeting(id=2, name='Garage Raceway', date=date(2024, 8, 1), venue='My Garage'),
        Meeting(id=3, name='Village Hall Grand Prix', date=date(2025, 2, 1), venue='Village Hall'),
        Meeting(id=4, name='2027 Village Hall Grand Prix', date=date(2027, 2, 1), venue='Village Hall')
    ])
    session.commit()


def add_meeting_drivers(session: Session):
    session.add_all([
        MeetingDriver(meeting_id=3, driver_id=1),
        MeetingDriver(meeting_id=3, driver_id=2),
        MeetingDriver(meeting_id=3, driver_id=3),
        MeetingDriver(meeting_id=3, driver_id=4),
        MeetingDriver(meeting_id=3, driver_id=5),
        MeetingDriver(meeting_id=3, driver_id=6),
        MeetingDriver(meeting_id=3, driver_id=7),
        MeetingDriver(meeting_id=3, driver_id=8),
        MeetingDriver(meeting_id=3, driver_id=9)
    ])
    session.commit()


def add_meeting_cars(session: Session):
    session.add_all([
        MeetingCar(meeting_id=3, car_id=1),
        MeetingCar(meeting_id=3, car_id=2),
        MeetingCar(meeting_id=3, car_id=3),
        MeetingCar(meeting_id=3, car_id=4),
        MeetingCar(meeting_id=3, car_id=5),
        MeetingCar(meeting_id=3, car_id=6)
    ])
    session.commit()


def add_sessions(session: Session):
    session.add_all([
        RaceSession(id=1, meeting_id=3, session_type='FastestLap', 
                   end_condition='Laps', end_condition_info=3, 
                   scoring_method='FastestLap', scoring_points=None,
                   start_time=time(14, 30, 0), end_time=time(15, 0, 0)),
        RaceSession(id=2, meeting_id=3, session_type='Points', 
                   end_condition='Laps', end_condition_info=20, 
                   scoring_method='PositionPoints', scoring_points=None,
                   start_time=time(15, 0, 0), end_time=None)
    ])
    session.commit()


def add_races(session: Session):
    session.add_all([
        Race(id=1, session_id=2, state='Finished'),
        Race(id=2, session_id=2, state='Finished'),
        Race(id=3, session_id=2, state='Running'),
        Race(id=4, session_id=2, state='NotStarted')
    ])
    session.commit()


def add_driver_races(session: Session):
    session.add_all([
        DriverRace(id=1, driver_id=1, race_id=2, car_id=1, lane=1),
        DriverRace(id=2, driver_id=2, race_id=2, car_id=1, lane=2),
        DriverRace(id=3, driver_id=3, race_id=2, car_id=2, lane=3),
        DriverRace(id=4, driver_id=4, race_id=2, car_id=3, lane=4),
        DriverRace(id=5, driver_id=5, race_id=2, car_id=4, lane=5),
        DriverRace(id=6, driver_id=6, race_id=2, car_id=5, lane=6),
        DriverRace(id=7, driver_id=1, race_id=1, car_id=1, lane=1),
        DriverRace(id=8, driver_id=1, race_id=3, car_id=1, lane=1),
        DriverRace(id=9, driver_id=2, race_id=4, car_id=2, lane=1),
    ])
    session.commit()


def add_driver_laps(session: Session):
    # Driver 1, 5 laps
    session.add_all([
        DriverLap(id=1, driver_race_id=1, lap_time=Decimal('12.345'), created_at=datetime(2024, 6, 1, 14, 30, 0)),
        DriverLap(id=2, driver_race_id=1, lap_time=Decimal('11.567'), created_at=datetime(2024, 6, 1, 14, 30, 10)),
        DriverLap(id=3, driver_race_id=1, lap_time=Decimal('9.789'), created_at=datetime(2024, 6, 1, 14, 30, 20)),
        DriverLap(id=4, driver_race_id=1, lap_time=Decimal('14.345'), created_at=datetime(2024, 6, 1, 14, 30, 30)),
        DriverLap(id=5, driver_race_id=1, lap_time=Decimal('16.678'), created_at=datetime(2024, 6, 1, 14, 30, 40))
    ])
    session.commit()
    
    # Driver 2, 6 laps
    session.add_all([
        DriverLap(id=6, driver_race_id=2, lap_time=Decimal('13.456'), created_at=datetime(2024, 6, 1, 14, 30, 0)),
        DriverLap(id=7, driver_race_id=2, lap_time=Decimal('12.678'), created_at=datetime(2024, 6, 1, 14, 30, 10)),
        DriverLap(id=8, driver_race_id=2, lap_time=Decimal('11.789'), created_at=datetime(2024, 6, 1, 14, 30, 20)),
        DriverLap(id=9, driver_race_id=2, lap_time=Decimal('10.345'), created_at=datetime(2024, 6, 1, 14, 30, 30)),
        DriverLap(id=10, driver_race_id=2, lap_time=Decimal('14.678'), created_at=datetime(2024, 6, 1, 14, 30, 40)),
        DriverLap(id=11, driver_race_id=2, lap_time=Decimal('15.789'), created_at=datetime(2024, 6, 1, 14, 30, 50))
    ])
    session.commit()
    
    # Driver 3, 2 laps
    session.add_all([
        DriverLap(id=12, driver_race_id=3, lap_time=Decimal('10.123'), created_at=datetime(2024, 6, 1, 14, 30, 0)),
        DriverLap(id=13, driver_race_id=3, lap_time=Decimal('11.456'), created_at=datetime(2024, 6, 1, 14, 30, 10))
    ])
    session.commit()
    
    # Driver 4, 5 laps
    session.add_all([
        DriverLap(id=14, driver_race_id=4, lap_time=Decimal('13.567'), created_at=datetime(2024, 6, 1, 14, 30, 0)),
        DriverLap(id=15, driver_race_id=4, lap_time=Decimal('12.789'), created_at=datetime(2024, 6, 1, 14, 30, 10)),
        DriverLap(id=16, driver_race_id=4, lap_time=Decimal('11.345'), created_at=datetime(2024, 6, 1, 14, 30, 20)),
        DriverLap(id=17, driver_race_id=4, lap_time=Decimal('14.678'), created_at=datetime(2024, 6, 1, 14, 30, 30)),
        DriverLap(id=18, driver_race_id=4, lap_time=Decimal('15.789'), created_at=datetime(2024, 6, 1, 14, 30, 40))
    ])
    session.commit()
    
    # Driver 5, 6 laps
    session.add_all([
        DriverLap(id=19, driver_race_id=5, lap_time=Decimal('12.123'), created_at=datetime(2024, 6, 1, 14, 30, 0)),
        DriverLap(id=20, driver_race_id=5, lap_time=Decimal('11.456'), created_at=datetime(2024, 6, 1, 14, 30, 10)),
        DriverLap(id=21, driver_race_id=5, lap_time=Decimal('10.789'), created_at=datetime(2024, 6, 1, 14, 30, 20)),
        DriverLap(id=22, driver_race_id=5, lap_time=Decimal('13.345'), created_at=datetime(2024, 6, 1, 14, 30, 30)),
        DriverLap(id=23, driver_race_id=5, lap_time=Decimal('14.678'), created_at=datetime(2024, 6, 1, 14, 30, 40)),
        DriverLap(id=24, driver_race_id=5, lap_time=Decimal('15.789'), created_at=datetime(2024, 6, 1, 14, 30, 50))
    ])
    session.commit()
    
    # Driver 6, 2 laps
    session.add_all([
        DriverLap(id=25, driver_race_id=6, lap_time=Decimal('12.345'), created_at=datetime(2024, 6, 1, 14, 30, 0)),
        DriverLap(id=26, driver_race_id=6, lap_time=Decimal('11.567'), created_at=datetime(2024, 6, 1, 14, 30, 10))
    ])
    session.commit()
    
    # Add the 6 lanes
    session.add_all([
        Lane(lane_number=1, color='red', enabled=True),
        Lane(lane_number=2, color='green', enabled=True),
        Lane(lane_number=3, color='blue', enabled=True),
        Lane(lane_number=4, color='yellow', enabled=True),
        Lane(lane_number=5, color='orange', enabled=True),
        Lane(lane_number=6, color="white", enabled=True)
    ])
    session.commit()





def drop_tables():
    try:
        settings = Settings()
        connection_string = f"postgresql://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_DATABASE}"
        print(f"Connection string: {connection_string}")
        engine = create_engine(connection_string)
    except Exception as e:
        print(f"Error creating engine: {e}")
        raise    
    SQLModel.metadata.drop_all(engine)

def create_db_and_tables():
    try:
        settings = Settings()
        connection_string = f"postgresql://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_DATABASE}"
        print(f"Connection string: {connection_string}")
        engine = create_engine(connection_string)
    except Exception as e:
        print(f"Error creating engine: {e}")
        raise    
    SQLModel.metadata.create_all(engine)

def add_sample_data():
    try:
        settings = Settings()
        connection_string = f"postgresql://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_DATABASE}"
        print(f"Connection string: {connection_string}")
        engine = create_engine(connection_string)
    except Exception as e:
        print(f"Error creating engine: {e}")
        raise    
    with Session(engine) as session:
        # Add data in the correct dependency order
        add_car_manufacturers(session)
        add_car_categories(session)
        add_car_models(session)
        add_car_tyres(session)
        add_chip_hardwares(session)
        add_chip_firmwares(session)
        add_cars(session)
        add_drivers(session)
        add_meetings(session)
        add_meeting_drivers(session)
        add_meeting_cars(session)
        add_sessions(session)
        add_races(session)
        add_driver_races(session)
        add_driver_laps(session)
    print("Sample data has been added successfully!")

if __name__ == "__main__":
    drop_tables()
    print("All tables dropped successfully")
    create_db_and_tables()
    print("All tables created successfully")
    add_sample_data()
    print("Sample data added successfully")



