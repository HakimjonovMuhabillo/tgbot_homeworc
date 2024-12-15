# main.py
import asyncio
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, Router, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ContentType, ReplyKeyboardRemove
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError

from config import TELEGRAM_TOKEN
from database import engine, Base, async_session
from model import Student, Homework, Submission, Teacher

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
import json
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import os
import logging

logging.basicConfig(level=logging.INFO)

# FSM Configuration
storage = MemoryStorage()


async def process_download(callback_query: types.CallbackQuery, submission_id: int):
	"""Процесс скачивания файла по его ID."""
	async with async_session() as session:
		try:
			# Получаем файл из базы данных
			submission_query = await session.execute(
				select(Submission).where(Submission.id == submission_id)
			)
			submission = submission_query.scalar_one_or_none()

			if not submission:
				await callback_query.message.answer("Файл не найден.")
				await callback_query.answer("Ошибка!")
				return

			# Отправляем файл через Telegram
			await bot.send_document(
				chat_id=callback_query.from_user.id,
				document=submission.file_id,
				caption=f"Файл: {submission.file_name}"
			)
			await callback_query.answer("Файл отправлен!")

		except SQLAlchemyError as e:
			logging.error(f"Ошибка при скачивании файла: {e}")
			await callback_query.message.answer("Ошибка при обработке запроса. Попробуйте позже.")
			await callback_query.answer("Ошибка!")


# FSM States
class HomeworkCreation(StatesGroup):
	waiting_for_description = State()
	waiting_for_deadline = State()


bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(storage=storage)
router = Router()

# Keyboards
teacher_menu = ReplyKeyboardMarkup(
	keyboard=[
		[KeyboardButton(text="Создать домашнее задание")],
		[KeyboardButton(text="Проверить домашки")],
		[KeyboardButton(text="Посмотреть домашнее задание")]
	],
	resize_keyboard=True,
)

student_menu = ReplyKeyboardMarkup(
	keyboard=[
		[KeyboardButton(text="Посмотреть домашнее задание")],
		[KeyboardButton(text="Отправить решение")],
	],
	resize_keyboard=True,
)
request_phone_menu = ReplyKeyboardMarkup(
	keyboard=[
		[KeyboardButton(text="Отправить номер телефона", request_contact=True)],
	],
	resize_keyboard=True,
	one_time_keyboard=True,
)


async def create_tables():
	"""Create tables in the database."""
	async with engine.begin() as conn:
		await conn.run_sync(Base.metadata.create_all)


import logging

# Configure logging
logging.basicConfig(level=logging.INFO)


class Registration(StatesGroup):
	waiting_for_phone = State()
	waiting_for_name = State()


@router.message(Command("start"))
async def start_command(message: types.Message, state: FSMContext):
	"""Handle /start command and initiate registration if not registered."""
	async with async_session() as session:
		try:
			teacher_query = await session.execute(
				select(Teacher).where(Teacher.telegram_id == str(message.from_user.id))
			)
			teacher = teacher_query.scalar_one_or_none()

			if teacher:
				await message.answer("Добро пожаловать, учитель!", reply_markup=teacher_menu)
				return

			student_query = await session.execute(
				select(Student).where(Student.telegram_id == str(message.from_user.id))
			)
			student = student_query.scalar_one_or_none()

			if student:
				await message.answer("Привет! Вы можете посмотреть или сдать домашнее задание.",
									 reply_markup=student_menu)
			else:
				await message.answer("Пожалуйста, отправьте ваш номер телефона.", reply_markup=request_phone_menu)
				await state.set_state(Registration.waiting_for_phone)

		except SQLAlchemyError as e:
			logging.error(f"Database error: {e}")
			await message.answer("Ошибка базы данных. Попробуйте позже.")


@router.message(Registration.waiting_for_phone)
async def handle_phone_number(message: types.Message, state: FSMContext):
	"""Handle phone number."""
	if message.contact and message.contact.user_id == message.from_user.id:
		await state.update_data(phone_number=message.contact.phone_number)
		await message.answer("Спасибо! Теперь отправьте ваше имя и фамилию (например, Иван Иванов).",
							 reply_markup=ReplyKeyboardRemove())
		await state.set_state(Registration.waiting_for_name)
	else:
		await message.answer("Пожалуйста, используйте кнопку для отправки номера телефона.")


@router.message(Registration.waiting_for_name)
async def handle_full_name(message: types.Message, state: FSMContext):
	"""Handle full name and complete registration."""
	async with async_session() as session:
		try:
			user_data = await state.get_data()
			phone_number = user_data.get("phone_number")
			full_name = message.text.strip()
			first_name, last_name = full_name.split(' ', 1) if ' ' in full_name else (full_name, '')

			new_student = Student(
				telegram_id=str(message.from_user.id),
				phone_number=phone_number,
				first_name=first_name,
				last_name=last_name,
				username=message.from_user.username,
			)
			session.add(new_student)
			await session.commit()

			await message.answer("Регистрация завершена! Вы можете посмотреть или сдать домашнее задание.",
								 reply_markup=student_menu)
			await state.clear()

		except SQLAlchemyError as e:
			await message.answer("Ошибка базы данных. Попробуйте позже.")
			logging.error(f"Database error: {e}")


@router.message(F.text == "Создать домашнее задание")
async def create_homework(message: types.Message, state: FSMContext):
	"""Учитель создает домашнее задание."""
	async with async_session() as session:
		teacher_query = await session.execute(
			select(Teacher).where(Teacher.telegram_id == str(message.from_user.id))
		)
		teacher = teacher_query.scalar_one_or_none()

		if not teacher:
			await message.answer("Вы не зарегистрированы как учитель.")
			return

		# Деактивируем существующее активное задание
		await session.execute(
			select(Homework).where(Homework.teacher_id == teacher.id, Homework.active == 1)
		)
		active_homework_query = await session.execute(
			select(Homework).where(Homework.teacher_id == teacher.id, Homework.active == 1)
		)
		active_homework = active_homework_query.scalars().first()

		if active_homework:
			active_homework.active = 1
			await session.commit()

		await message.answer("Введите описание домашнего задания:")
		await state.set_state(HomeworkCreation.waiting_for_description)


@router.message(F.text == "Посмотреть домашнее задание")
async def view_homework(message: types.Message):
	"""Просмотр единственного активного домашнего задания."""
	async with async_session() as session:
		try:
			# Получаем единственное активное задание
			homework_query = await session.execute(select(Homework).order_by(Homework.deadline))
			homeworks = homework_query.scalars().all()

			homework_list = "\n".join([f"Описание: {hw.description}, Срок сдачи: {hw.deadline}" for hw in homeworks])

			if homeworks:
				await message.answer(f"Домашние задания:\n{homework_list}")
			else:
				await message.answer("На данный момент нет активных домашних заданий.")
		except SQLAlchemyError as e:
			print(e)
			await message.answer("Ошибка при получении данных. Попробуйте позже.")


# @router.message(F.text == "Проверить домашки")
# async def review_submissions(message: types.Message):
#     """Учитель проверяет отправленные решения."""
#     async with async_session() as session:
#         try:
#             teacher_query = await session.execute(
#                 select(Teacher).where(Teacher.telegram_id == str(message.from_user.id))
#             )
#             teacher = teacher_query.scalar_one_or_none()
#
#             if not teacher:
#                 await message.answer("Вы не зарегистрированы как учитель.")
#                 return
#
#             # Получаем активное задание
#             homework_query = await session.execute(
#                 select(Homework).where(Homework.active == 1, Homework.teacher_id == teacher.id)
#             )
#             homework = homework_query.scalar_one_or_none()
#
#             if not homework:
#                 await message.answer("Нет активных домашних заданий для проверки.")
#                 return
#
#             # Получаем список отправленных решений
#             submission_query = await session.execute(
#                 select(Submission).where(Submission.homework_id == homework.id)
#             )
#             submissions = submission_query.scalars().all()
#
#             if not submissions:
#                 await message.answer("Для этого задания еще нет отправленных решений.")
#                 return
#
#             # Формируем список решений
#             for submission in submissions:
#                 await message.answer(
#                     f"📄 Имя файла: {submission.file_name}\n"
#                     f"📅 Отправлено: {submission.created_at:%Y-%m-%d %H:%M}\n"
#                     f"👤 Студент ID: {submission.student_id}\n"
#                     f"🎓 Оценка: {submission.grade if submission.grade is not None else 'Не оценено'}"
#                 )
#         except SQLAlchemyError as e:
#             logging.error(f"Ошибка при проверке решений: {e}")
#             await message.answer("Ошибка при получении данных. Попробуйте позже.")


# Ensure logging is configured at the beginning of your script


# Ensure logging is configured at the beginning of your script


# Ensure logging is configured at the beginning of your script
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


@router.message(F.text == "Проверить домашки")
async def review_submissions(message: types.Message):
	"""Учитель проверяет отправленные решения."""
	async with async_session() as session:
		try:
			teacher_query = await session.execute(
				select(Teacher).where(Teacher.telegram_id == str(message.from_user.id))
			)
			teacher = teacher_query.scalars().unique().first()

			if not teacher:
				await message.answer("Вы не зарегистрированы как учитель.")
				return

			homework_query = await session.execute(
				select(Homework).where(Homework.active == 1, Homework.teacher_id == teacher.id)
			)
			homework = homework_query.scalars().first()

			if not homework:
				await message.answer("Нет активных домашних заданий для проверки.")
				return

			students_query = await session.execute(select(Student))
			students = students_query.scalars().all()

			student_dict = {student.id: student for student in students}

			submission_query = await session.execute(
				select(Submission).where(Submission.homework_id == homework.id)
			)
			submissions = submission_query.scalars().all()

			submitted_students_ids = {submission.student_id for submission in submissions}
			submitted_students = [student for student in students if student.id in submitted_students_ids]
			not_submitted_students = [student for student in students if student.id not in submitted_students_ids]

			submitted_list = "\n".join([f"{student.first_name} {student.last_name}" for student in submitted_students])
			not_submitted_list = "\n".join(
				[f"{student.first_name} {student.last_name}" for student in not_submitted_students]
			)

			keyboard = InlineKeyboardMarkup(
				inline_keyboard=[
					[
						InlineKeyboardButton(
							text=f"{submission.file_names} (от {student_dict[submission.student_id].first_name} {student_dict[submission.student_id].last_name})",
							callback_data=json.dumps({"action": "select_submission", "id": submission.id}),
						)
					]
					for submission in submissions
				]
			)

			await message.answer(
				f"Студенты, отправившие решения:\n{submitted_list}\n\nСтуденты, не отправившие решения:\n{not_submitted_list}"
			)
			await message.answer("Выберите файл для скачивания:", reply_markup=keyboard)
			logging.info("Reviewed submissions and displayed to teacher.")
		except SQLAlchemyError as e:
			logging.error(f"Ошибка при проверке решений: {e}")
			await message.answer("Ошибка при получении данных. Попробуйте позже.")


@router.callback_query(lambda c: json.loads(c.data).get("action") == "select_submission")
async def handle_submission_selection(callback_query: types.CallbackQuery, state: FSMContext):
	"""Обработка выбора файла для проверки."""
	data = json.loads(callback_query.data)
	submission_id = data.get("id")
	logging.info(f"Callback data: {data}")

	async with async_session() as session:
		try:
			submission_query = await session.execute(
				select(Submission).where(Submission.id == submission_id)
			)
			submission = submission_query.scalar_one_or_none()

			if not submission:
				await callback_query.message.answer("Решение не найдено.")
				await callback_query.answer()
				return

			# Store the selected submission ID in the state
			await state.update_data(selected_submission_id=submission_id)

			# Send each file as a separate document
			for file_id in submission.file_ids:
				await bot.send_document(callback_query.from_user.id, file_id)

			keyboard = InlineKeyboardMarkup(
				inline_keyboard=[
					[
						InlineKeyboardButton(
							text="Оценить",
							callback_data=json.dumps({"action": "grade_submission"})
						)
					]
				]
			)
			await callback_query.message.answer(
				f"Вы выбрали решение #{submission_id}. Нажмите на кнопку ниже, чтобы оценить.",
				reply_markup=keyboard
			)
			await callback_query.answer()
			logging.info(f"Selected submission #{submission_id} for review and sent documents.")
		except SQLAlchemyError as e:
			logging.error(f"Ошибка при обработке выбора файла: {e}")
			await callback_query.message.answer("Ошибка при обработке выбора файла. Попробуйте позже.")
			await callback_query.answer()


@router.callback_query(lambda c: json.loads(c.data).get("action") == "grade_submission")
async def prompt_for_grade(callback_query: types.CallbackQuery):
	"""Промпт для ввода оценки."""
	await callback_query.message.answer(
		"Введите оценку."
	)
	await callback_query.answer()
	logging.info("Prompted teacher for grade input.")


@router.message(F.text.regexp(r'^\d+$'))
async def grade_submission(message: types.Message, state: FSMContext):
	"""Учитель оценивает отправленное решение и начисляет бонусные баллы."""
	async with async_session() as session:
		try:
			state_data = await state.get_data()
			submission_id = state_data.get("selected_submission_id")

			if not submission_id:
				await message.answer("Сначала выберите решение для оценки.")
				return

			grade_str = message.text
			try:
				grade = int(grade_str)
			except ValueError:
				await message.answer("Оценка должна быть числом.")
				return

			# Calculate bonus points
			bonus_points = {
				5: 3,
				4: 2,
				3: 1,
				2: 0,
				1: 0  # Assuming any grade lower than 2 gets 0 points
			}.get(grade, 0)

			submission_query = await session.execute(
				select(Submission).where(Submission.id == submission_id)
			)
			submission = submission_query.scalar_one_or_none()

			if not submission:
				await message.answer("Решение не найдено.")
				return

			submission.grade = grade
			submission.bonus_points = bonus_points
			submission.is_reviewed = True
			await session.commit()

			await message.answer(
				f"Решение #{submission_id} оценено на {grade} баллов и начислено {bonus_points} бонусных баллов.")
			logging.info(
				f"Submission #{submission_id} graded with {grade} points and awarded {bonus_points} bonus points.")
		except (ValueError, SQLAlchemyError) as e:
			logging.error(f"Ошибка при выставлении оценки: {e}")
			await message.answer("Ошибка при выставлении оценки. Убедитесь, что команда введена корректно.")


@router.callback_query()
async def handle_callback(callback_query: types.CallbackQuery):
	"""Обработка всех callback-запросов."""
	try:
		# Распаковываем данные из callback_data
		data = json.loads(callback_query.data)

		if data.get("action") == "download":
			await process_download(callback_query, data["id"])

	except (ValueError, KeyError):
		await callback_query.answer("Ошибка обработки данных.")


@router.message(F.text.startswith("Скачать"))
async def download_submission(message: types.Message):
	"""Скачивание отправленного файла."""
	async with async_session() as session:
		try:
			# Извлекаем имя файла из текста сообщения
			file_name = message.text.replace("Скачать ", "").strip()

			# Ищем запись в базе данных
			submission_query = await session.execute(
				select(Submission).where(Submission.file_name == file_name)
			)
			submission = submission_query.scalar_one_or_none()

			if not submission:
				await message.answer("Файл не найден.")
				return

			# Проверяем, существует ли файл на сервере
			try:
				# Отправляем файл из Telegram
				await bot.send_document(
					chat_id=message.from_user.id,
					document=submission.file_id,
					caption=f"Файл: {submission.file_name}"
				)
				await message.answer("Файл успешно отправлен.")
			except Exception as e:
				logging.error(f"Ошибка при отправке файла из Telegram: {e}")
				await message.answer("Не удалось отправить файл. Попробуйте позже.")

		except SQLAlchemyError as e:
			logging.error(f"Ошибка при скачивании файла: {e}")
			await message.answer("Ошибка при обработке запроса. Попробуйте позже.")


# Ensure logging is configured at the beginning of your script

# Ensure logging is configured at the beginning of your script


@router.message(F.text == "Отправить решение")
async def ask_for_submission(message: types.Message, state: FSMContext):
	"""Initiate the file submission process."""
	async with async_session() as session:
		try:
			homework_query = await session.execute(
				select(Homework).where(Homework.active == 1)
			)
			homework = homework_query.scalars().first()

			if homework:
				await state.update_data(
					submission_in_progress=True,
					file_ids=[],
					file_names=[]
				)
				await message.answer(
					"Отправьте файлы с решением в формате документа. Вы можете отправить несколько файлов.")
			else:
				await message.answer("На данный момент нет активных домашних заданий.")
		except SQLAlchemyError as e:
			logging.error(f"Ошибка при проверке домашнего задания: {e}")
			await message.answer("Ошибка при проверке домашнего задания. Попробуйте позже.")


@router.message(F.text == "Отправить решение")
async def ask_for_submission(message: types.Message, state: FSMContext):
	"""Initiate the file submission process."""
	async with async_session() as session:
		try:
			homework_query = await session.execute(
				select(Homework).where(Homework.active == 1)
			)
			homework = homework_query.scalars().first()

			if homework:
				await state.update_data(
					submission_in_progress=True,
					file_ids=[],
					file_names=[]
				)
				await message.answer(
					"Отправьте файлы с решением в формате документа. Вы можете отправить несколько файлов.")
			else:
				await message.answer("На данный момент нет активных домашних заданий.")
		except SQLAlchemyError as e:
			logging.error(f"Ошибка при проверке домашнего задания: {e}")
			await message.answer("Ошибка при проверке домашнего задания. Попробуйте позже.")


@router.message(F.content_type == ContentType.DOCUMENT)
async def handle_submission(message: types.Message, state: FSMContext):
	"""Process the submitted files and save them as a single submission."""
	async with async_session() as session:
		try:
			# Check if there is an active homework
			homework_query = await session.execute(
				select(Homework).where(Homework.active == 1)
			)
			homework = homework_query.scalars().first()

			if not homework:
				await message.answer("Currently, there are no active assignments.")
				return

			# Check if the user is registered as a student
			student_query = await session.execute(
				select(Student).where(Student.telegram_id == str(message.from_user.id))
			)
			student = student_query.scalar_one_or_none()

			if not student:
				await message.answer("You are not registered as a student.")
				return

			# Validate deadline
			deadline = homework.deadline.replace(tzinfo=None) if homework.deadline.tzinfo else homework.deadline
			current_time = datetime.now()
			if current_time > deadline:
				await message.answer(
					f"The deadline for the assignment has passed ({deadline.strftime('%Y-%m-%d %H:%M:%S')}). You cannot submit your solution."
				)
				return

			# Get state data
			state_data = await state.get_data()
			submission_in_progress = state_data.get("submission_in_progress", False)

			if not submission_in_progress:
				await message.answer("Please start the submission process by clicking 'Отправить решение'.")
				return

			# Save file details to the state
			file_ids = state_data.get("file_ids", [])
			file_names = state_data.get("file_names", [])
			file_ids.append(message.document.file_id)
			file_names.append(message.document.file_name)

			await state.update_data(file_ids=file_ids, file_names=file_names)

			# Save the file locally
			directory = 'submissions'
			if not os.path.exists(directory):
				os.makedirs(directory)

			file_path = os.path.join(directory, f"{student.id}_{homework.id}_{message.document.file_name}")
			await bot.download(message.document, destination=file_path)

			await message.answer(
				f"Файл '{message.document.file_name}' успешно загружен. Отправьте другие файлы или отправьте <Завершить отправку> чтоб завершить процесс.")

		except SQLAlchemyError as e:
			await message.answer("An error occurred while saving. Please try again later.")
			logging.error(f"SQLAlchemyError: {e}")


@router.message(F.text == "Завершить отправку")
async def finalize_submission(message: types.Message, state: FSMContext):
	"""Finalize the submission process and save the submission."""
	async with async_session() as session:
		try:
			state_data = await state.get_data()
			file_ids = state_data.get("file_ids", [])
			file_names = state_data.get("file_names", [])

			# Ensure files were uploaded
			if not file_ids or not file_names:
				await message.answer("Вы не загрузили ни одного файла.")
				return

			# Check if there is an active homework
			homework_query = await session.execute(
				select(Homework).where(Homework.active == 1)
			)
			homework = homework_query.scalars().first()

			if not homework:
				await message.answer("Currently, there are no active assignments.")
				return

			# Check if the user is registered as a student
			student_query = await session.execute(
				select(Student).where(Student.telegram_id == str(message.from_user.id))
			)
			student = student_query.scalar_one_or_none()

			if not student:
				await message.answer("You are not registered as a student.")
				return

			# Check submission attempts
			submission_query = await session.execute(
				select(Submission).where(
					Submission.student_id == student.id,
					Submission.homework_id == homework.id
				)
			)
			submission_count = len(submission_query.scalars().all())

			if submission_count >= homework.max_attempts:
				await message.answer("You have used all submission attempts.")
				return

			# Save the submission to the database
			submission = Submission(
				student_id=student.id,
				homework_id=homework.id,
				file_ids=file_ids,
				file_names=file_names,
				created_at=datetime.utcnow(),
			)
			session.add(submission)
			await session.commit()

			# Notify the teacher
			teacher_query = await session.execute(
				select(Teacher).where(Teacher.id == homework.teacher_id)
			)
			teacher = teacher_query.scalar_one_or_none()

			if teacher:
				await bot.send_message(
					teacher.telegram_id,
					f"Student {message.from_user.full_name} has submitted their solution for the assignment '{homework.description}'."
				)

			await message.answer("Ваше решение успешно отправлено и сохранено.")
			await state.clear()

		except SQLAlchemyError as e:
			await message.answer("An error occurred while saving. Please try again later.")
			logging.error(f"SQLAlchemyError: {e}")


@router.message(HomeworkCreation.waiting_for_description)
async def set_deadline(message: types.Message, state: FSMContext):
	"""Переход к установке дедлайна."""
	await state.update_data(description=message.text)
	await message.answer("Теперь укажите дедлайн для домашнего задания (в формате: YYYY-MM-DD HH:MM):")
	await state.set_state(HomeworkCreation.waiting_for_deadline)


@router.message(HomeworkCreation.waiting_for_deadline)
async def save_homework(message: types.Message, state: FSMContext):
	"""Сохранение домашнего задания."""
	async with async_session() as session:
		try:
			try:
				deadline = datetime.strptime(message.text, "%Y-%m-%d %H:%M")
				if deadline <= datetime.now():
					await message.answer("Дедлайн должен быть в будущем. Попробуйте снова:")
					return
			except ValueError:
				await message.answer("Некорректный формат даты. Укажите дату в формате: YYYY-MM-DD HH:MM")
				return

			data = await state.get_data()
			description = data.get("description")

			teacher_query = await session.execute(
				select(Teacher).where(Teacher.telegram_id == str(message.from_user.id))
			)
			teacher = teacher_query.scalar_one_or_none()

			if not teacher:
				await message.answer("Вы не зарегистрированы как учитель.")
				await state.clear()
				return

			new_homework = Homework(
				description=description,
				deadline=deadline,
				max_attempts=3,
				active=1,
				teacher_id=teacher.id
			)
			session.add(new_homework)
			await session.commit()

			await message.answer("Домашнее задание успешно создано!", reply_markup=teacher_menu)
			await state.clear()

		except SQLAlchemyError:
			await message.answer("Ошибка при создании задания. Попробуйте позже.")
			await state.clear()


async def main():
	"""Run the bot."""
	await create_tables()
	dp.include_router(router)
	await dp.start_polling(bot)


if __name__ == "__main__":
	asyncio.run(main())
