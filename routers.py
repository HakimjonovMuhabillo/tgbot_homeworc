from datetime import timedelta, datetime

from aiogram import F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from gpt.database import async_session
from gpt.main import router, student_menu, teacher_menu
from gpt.model import Homework, Teacher, Student


@router.message(F.text == "Регистрация учителя")
async def register_teacher(message: types.Message):
    """Регистрация учителя."""
    async with async_session() as session:
        try:
            teacher_query = await session.execute(
                select(Teacher).where(Teacher.telegram_id == str(message.from_user.id))
            )
            teacher = teacher_query.scalar_one_or_none()

            if teacher:
                await message.answer("Вы уже зарегистрированы как учитель!", reply_markup=teacher_menu)
                return

            new_teacher = Teacher(
                telegram_id=str(message.from_user.id),
                name=message.from_user.full_name or "Unknown"
            )
            session.add(new_teacher)
            await session.commit()
            await message.answer("Вы успешно зарегистрированы как учитель!", reply_markup=teacher_menu)
        except SQLAlchemyError as e:
            await message.answer("Ошибка при регистрации. Попробуйте позже.")


@router.message(F.text == "Регистрация студента")
async def register_student(message: types.Message):
    """Регистрация студента."""
    async with async_session() as session:
        try:
            student_query = await session.execute(
                select(Student).where(Student.telegram_id == str(message.from_user.id))
            )
            student = student_query.scalar_one_or_none()

            if student:
                await message.answer("Вы уже зарегистрированы как студент!", reply_markup=student_menu)
                return

            new_student = Student(
                telegram_id=str(message.from_user.id),
                name=message.from_user.full_name or "Unknown"
            )
            session.add(new_student)
            await session.commit()
            await message.answer("Вы успешно зарегистрированы как студент!", reply_markup=student_menu)
        except SQLAlchemyError as e:
            await message.answer("Ошибка при регистрации. Попробуйте позже.")


@router.message(F.text == "Создать домашнее задание")
async def create_homework(message: types.Message):
    """Учитель создает домашнее задание."""
    await message.answer("Введите описание домашнего задания:")

    @router.message(F.text)
    async def save_homework(message: types.Message):
        """Сохранение домашнего задания."""
        async with async_session() as session:
            try:
                teacher_query = await session.execute(
                    select(Teacher).where(Teacher.telegram_id == str(message.from_user.id))
                )
                teacher = teacher_query.scalar_one_or_none()

                if not teacher:
                    await message.answer("Вы не зарегистрированы как учитель.")
                    return

                new_homework = Homework(
                    description=message.text,
                    deadline=datetime.now() + timedelta(days=7),
                    max_attempts=3,
                    active=1,
                    teacher_id=teacher.id
                )
                session.add(new_homework)
                await session.commit()
                await message.answer("Домашнее задание успешно создано!", reply_markup=teacher_menu)
            except SQLAlchemyError as e:
                await message.answer("Ошибка при создании задания. Попробуйте позже.")


@router.message(F.text == "Проверить домашки")
async def review_homework(message: types.Message):
    """Учитель проверяет отправленные домашки."""
    async with async_session() as session:
        try:
            teacher_query = await session.execute(
                select(Teacher).where(Teacher.telegram_id == str(message.from_user.id))
            )
            teacher = teacher_query.scalar_one_or_none()

            if not teacher:
                await message.answer("Вы не зарегистрированы как учитель.")
                return

            homeworks_query = await session.execute(
                select(Homework).where(Homework.teacher_id == teacher.id)
            )
            homeworks = homeworks_query.scalars().all()

            if not homeworks:
                await message.answer("У вас пока нет созданных домашних заданий.")
                return

            buttons = [
                [InlineKeyboardButton(text=f"Домашка ID: {hw.id}", callback_data=f"review_hw_{hw.id}")]
                for hw in homeworks
            ]
            markup = InlineKeyboardMarkup(inline_keyboard=buttons)
            await message.answer("Выберите домашнее задание для проверки:", reply_markup=markup)
        except SQLAlchemyError as e:
            await message.answer("Ошибка базы данных. Попробуйте позже.")


@router.message(F.text == "Отправить решение")
async def ask_for_submission(message: types.Message):
    """Студент отправляет решение."""
    await message.answer("Отправьте файл с решением.")


@router.message(F.text == "Посмотреть домашнее задание")
async def view_homework(message: types.Message):
    """Просмотр активного домашнего задания."""
    async with async_session() as session:
        try:
            homework_query = await session.execute(
                select(Homework).where(Homework.active == 1)
            )
            homework = homework_query.scalar_one_or_none()

            if homework:
                await message.answer(
                    f"Домашнее задание:\n{homework.description}\n"
                    f"Дедлайн: {homework.deadline:%Y-%m-%d %H:%M}\n"
                    f"Максимальное количество попыток: {homework.max_attempts}"
                )
            else:
                await message.answer("Нет активных домашних заданий.")
        except SQLAlchemyError as e:
            await message.answer("Ошибка при получении данных. Попробуйте позже.")
