import csv
import io

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message

from bot import db, texts
from bot.common import guard, require_user

router = Router()


def csv_safe(value) -> str:
    result = str(value if value is not None else '')
    return "'" + result if result.lstrip().startswith(('=', '+', '-', '@')) else result


def report_csv(report: dict) -> bytes:
    buffer = io.StringIO(newline='')
    writer = csv.writer(buffer)
    writer.writerow(texts.CSV_COLUMNS)
    writer.writerow(
        [
            csv_safe(report['school']),
            csv_safe(report['class']),
            report['students_count'],
            report['answers_count'],
            report['error_rate'],
        ]
    )
    writer.writerow([])
    writer.writerow(texts.CSV_STUDENTS)
    for row in report.get('top_students', []):
        writer.writerow([csv_safe(row['name']), row['points'], row['level'], row['answers']])
    writer.writerow([])
    writer.writerow(texts.CSV_DAYS)
    for day in report.get('activity', []):
        writer.writerow([day['day'], day['answers']])
    writer.writerow([])
    writer.writerow(texts.CSV_PROGRESS)
    for row in report.get('students_progress', []):
        writer.writerow(
            [
                csv_safe(row.get('name')),
                row.get('today_answers'),
                texts.YES if row.get('completed') else texts.NO,
            ]
        )
    writer.writerow([])
    writer.writerow(texts.CSV_MISTAKES)
    for row in report.get('frequent_mistakes', []):
        writer.writerow([csv_safe(row.get('text_ba')), row.get('lang_pair'), row.get('errors')])
    return ('\ufeff' + buffer.getvalue()).encode('utf-8')


@router.message(Command('me'))
@guard
async def me(message: Message) -> None:
    user = await require_user(message)
    if not user:
        return
    if not user.get('nickname'):
        await message.answer(texts.REGISTRATION_REQUIRED)
        return
    stats = await db.user_stats(user['id'])
    badges = await db.user_badges(user['id'])
    goal = await db.daily_goal()
    await message.answer(texts.profile(user, stats, badges, goal))


@router.message(Command('report'))
@guard
async def report(message: Message) -> None:
    user = await require_user(message)
    if not user:
        return
    if user.get('role') != 'teacher' or not user.get('class_id'):
        await message.answer(texts.NO_REPORT_ACCESS)
        return
    secret = await db.class_secret(user['class_id'])
    if not secret:
        await message.answer(texts.NO_CLASS)
        return
    data = await db.rpc('get_class_report', {'p_teacher_code': secret})
    await message.answer(texts.report(data))
    await message.answer_document(BufferedInputFile(report_csv(data), 'class_report.csv'))


@router.message(Command('help'))
@guard
async def help_command(message: Message) -> None:
    await message.answer(texts.HELP)
