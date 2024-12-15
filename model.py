from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


# Tables
class Teacher(Base):
	__tablename__ = "teachers"

	id = Column(Integer, primary_key=True, autoincrement=True)
	telegram_id = Column(String(50), unique=True, nullable=False)
	name = Column(String(100), nullable=False)


class Homework(Base):
	__tablename__ = "homeworks"

	id = Column(Integer, primary_key=True, autoincrement=True)
	description = Column(Text, nullable=False)
	deadline = Column(DateTime, nullable=False)
	max_attempts = Column(Integer, default=3)
	active = Column(Integer, default=1)
	teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=False)

	# Relationship: one homework can have many submissions
	submissions = relationship("Submission", back_populates="homework")


class Student(Base):
	__tablename__ = "students"

	id = Column(Integer, primary_key=True, autoincrement=True)
	telegram_id = Column(String(50), unique=True, nullable=False)
	phone_number = Column(String(15), unique=True, nullable=False)
	first_name = Column(String(50), nullable=False)
	last_name = Column(String(50), nullable=False)
	username = Column(String(50), unique=True, nullable=False)
	total_points = Column(Integer, default=0)

	# Relationship: one student can have many submissions
	submissions = relationship("Submission", back_populates="student")


class Submission(Base):
	__tablename__ = "submissions"

	id = Column(Integer, primary_key=True, autoincrement=True)
	student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
	homework_id = Column(Integer, ForeignKey("homeworks.id"), nullable=False)
	file_ids = Column(JSON, nullable=False, default=list)  # Field to store multiple file IDs
	file_names = Column(JSON, nullable=False, default=list)  # Field to store multiple file names
	created_at = Column(DateTime, default=datetime.utcnow)
	grade = Column(Integer, nullable=True)  # Field for grade
	is_reviewed = Column(Boolean, default=False)

	# Relationships
	student = relationship("Student", back_populates="submissions")
	homework = relationship("Homework", back_populates="submissions")
