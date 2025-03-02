"""
Новая версия обработчика. Теперь буду с файла читать не бинарные строки,
а просто фиксированными блоками (чтение строками приводит к разделению строки
внутри блока stream и ошибкам)

Добавление от 11.07.23: в процессе разбирания с pdf понял, как правильно
его читать (сначала таблицу xref, а потом уже на её основе список страниц),
но нашел готовую библиотеку prdrw и использовал её. Теперь не падает
ни только на файлах мая 2023, но и на файле единого счета - можно просто 
закидывать весь массив счетов. Вроде как эта схема теперь считывает весь файл целиком,
но по памяти не падает - но это нужно проверить по-хорошему (у меня итераторы,
но исходно для pdfrw вроде как полный read() по файлам отдается)
"""


import csv
from glob import glob
import re
import zlib


"""
Функция проверяет, что список из 5 строк является
строкой из раздела 'Разовые начисления'.
Проверки следующие:
- все 5 строк не None
- первое значение попадает под маску 'ровно 10 цифр'
- второе значение не None
- третье и четвертое значения типа Float (можно конвертировать)
- пятое значение можно конвертировать в integer
Если все проверки прошли, то возвращается True, иначе False
"""
def check_for_line_in_block_onetime_charges(list_of_5_strings):
    for string in list_of_5_strings:
        if string == None:
            return False
    if not (list_of_5_strings[0].isdigit() and len(list_of_5_strings[0]) == 10):
        return False
    if re.match(r"^-?\d+(?:\.\d+)$", list_of_5_strings[2]) is None:
        return False
    if re.match(r"^-?\d+(?:\.\d+)$", list_of_5_strings[3]) is None:
        return False
    # в количестве бывает цифра в виде "   1", поэтому функция strip
    if not list_of_5_strings[4].strip().isdigit():
        return False
    return True


def pdfrw_read(file):
    """
    Использую библиотеку pdfrw для чтения
    потоков из файла.
    Возвращает распакованное содержимое stream
    Выходной формат оставил такой же, как у line_marking
    Но физически наличие stream у страницы и что
    есть флаг /Filter /FlatDecode не проверяю
    (если будет где-то страница без этого, то ошибка будет)
    """
    from pdfrw import PdfReader
    fdata = file.read()
    x = PdfReader(fdata=fdata)
    for page in x.pages:
        stream_line = bytes(page.Contents.stream, 'latin-1')
        yield {
                    "object_type": "stream_line",
                    "stream_line": stream_line,
                    "flags": {"filter": True}
                    }


def stream_decoding(lines_of_stream):
    # обрабатываю только строки с "object_type" == "stream_line",
    # остальные игнорирую
    for stream_line in lines_of_stream:
        if stream_line["object_type"] == "stream_line":
            if stream_line["flags"]["filter"]:
                # декодируем только, если встретился filter
                stream_line_decode = zlib.decompress(
                    stream_line["stream_line"]
                )
            else:
                stream_line_decode = stream_line["stream_line"]
            # позиция начала текста в потоке
            pos_begin = stream_line_decode.find(b"TD\n(")
            pos_end = None  # позиция скобки после текста в потоке
            if pos_begin != -1:
                while pos_begin != -1:
                    # скобка ')' - конец текста
                    pos_end = stream_line_decode.find(b")", pos_begin)
                    # но встречаются последовательности '\\)' -
                    # такое является частью текста,
                    # соответственно, проверяю найденное вхождение,
                    # если оно часть текста, то двигаю pos_end
                    pos_double_slash = stream_line_decode.find(
                        b"\\)",
                        pos_end-1,
                        pos_end+1
                    )
                    while pos_double_slash != -1:
                        pos_end = stream_line_decode.find(b")", pos_end + 1)
                        pos_double_slash = stream_line_decode.find(
                            b"\\)",
                            pos_end-1,
                            pos_end+1
                        )
                    yield stream_line_decode[pos_begin+4: pos_end].replace(
                        b"\\)",
                        b")"
                        ).replace(b"\\(", b"(").decode("1251")
                    pos_begin = stream_line_decode.find(
                        b"TD\n(",
                        pos_begin + 1
                        )


# Функция ищет строки со словами "ПриорОбслАгент"
# Возвращает по каждому нахождению словарь из 5 позиций:
# phone - номер телефона
# from_date - с какой даты
# to_date - по какую дату
# service_name - название услуги
# fee - начисления по услуге
# При нахождении строки "Детализация" прекращает работу
# (чтобы обрабатывать только приложение к счету)
# Реализация. Запоминаем 5 предыдущих строк. И последовательно сдвигаем
# Если в 5-й строке "ПриорОбсАгент", то формируем выходную строку
def agprior_searching(list_of_strings):
    list_of_6_strings = [None, None, None, None, None, None]
    # Буду ставить в True после строки "Разовые начисления"
    # Буду возвращать в False после строки "Приложение к счету №"
    # Буду возвращать в False после строки "Скидки и надбавки"
    # Буду возвращать в False после строки "Перенос начислений в Единый счет"
    onetime_charges = False
    for string in list_of_strings:

        if string.find("Разовые начисления") != -1:
            onetime_charges = True

        if string.find("Приложение к счету №") != -1:
            onetime_charges = False

        if string.find("Cкидки и надбавки") != -1:
            onetime_charges = False

        if string.find("Перенос начислений в Единый счет") != -1:
            onetime_charges = False

        # Прерываем обработку на блоке
        # "Использование включённого трафика и корректировки"
        # (дальше уже ничего нужного не может быть: прерываем, 
        # чтобы не тратить время впустую)
        if string.find("Использование включённого трафика и корректировки") != -1:
            print("Использование включённого трафика и корректировки")
            break

        # Если не будет блока про использование трафика, прервемся на детализации
        if string.find("Детализация") != -1:
            print("Детализация")
            break
        elif list_of_6_strings[0] is None:
            list_of_6_strings[0] = string
        elif list_of_6_strings[1] is None:
            list_of_6_strings[1] = string
        elif list_of_6_strings[2] is None:
            list_of_6_strings[2] = string
        elif list_of_6_strings[3] is None:
            list_of_6_strings[3] = string
        elif list_of_6_strings[4] is None:
            list_of_6_strings[4] = string
        else:
            if list_of_6_strings[5] is not None:
                # если в последней ячейке что-то есть, делаю сдвиг
                list_of_6_strings[0] = list_of_6_strings[1]
                list_of_6_strings[1] = list_of_6_strings[2]
                list_of_6_strings[2] = list_of_6_strings[3]
                list_of_6_strings[3] = list_of_6_strings[4]
                list_of_6_strings[4] = list_of_6_strings[5]
            list_of_6_strings[5] = string
            if list_of_6_strings[4].find("ПриорОбслАгент") != -1:
                yield {
                    "phone": list_of_6_strings[0],
                    "from_date": list_of_6_strings[1],
                    "to_date": list_of_6_strings[3],
                    "service_name": list_of_6_strings[4],
                    # меняем точку на запятую, чтобы excel корректно читал
                    "fee": list_of_6_strings[5].replace(".", ","),
                    "type": "agprior"
                    }
            elif onetime_charges:
                if check_for_line_in_block_onetime_charges(list_of_6_strings[:5]):
                    yield {
                        "phone": list_of_6_strings[0],
                        "description": list_of_6_strings[1],
                        # меняем точку на запятую, чтобы excel корректно читал
                        "charge": list_of_6_strings[2].replace(".", ","),
                        "quantity": list_of_6_strings[4].strip(),
                        # меняем точку на запятую, чтобы excel корректно читал
                        "summa": list_of_6_strings[3].replace(".", ","),
                        "type": "one_time_charges"
                    }


# MAIN
# Инициализирую выгрузку в csv (AGPRIOR)
fields = ["phone", "from_date", "to_date", "service_name", "fee", "type"]
FILE_NAME_AGPRIOR = "pdf\\agprior.csv"
csv.register_dialect("my_dialect", delimiter=";", lineterminator="\n")
with open(FILE_NAME_AGPRIOR, "w", encoding="1251") as f_out:
    writer = csv.DictWriter(f_out, fields, dialect="my_dialect")
    writer.writeheader()

# Инициализирую выгрузку в csv (ONE_TIME_CHARGE)
fields_otc = ["phone", "description", "charge", "quantity", "summa", "type"]
FILE_NAME_ONE_TIME_CHARGE = "pdf\\onecharge.csv"
with open(FILE_NAME_ONE_TIME_CHARGE, "w", encoding="1251") as f_otc_out:
    writer = csv.DictWriter(f_otc_out, fields_otc, dialect="my_dialect")
    writer.writeheader()

list_of_pdf = glob("pdf\\*.pdf")
for pdf_file in list_of_pdf:
    print(f"Файл: {pdf_file}")
    with open(pdf_file, "rb") as f:
        line_with_obj = pdfrw_read(f)
        decoding_line = stream_decoding(line_with_obj)
        agprior_line = agprior_searching(decoding_line)
        with open(FILE_NAME_AGPRIOR, "a", encoding="1251") as f_out:
            writer = csv.DictWriter(f_out, fields, dialect="my_dialect")
            with open(FILE_NAME_ONE_TIME_CHARGE, "a", encoding="1251") as f_otc_out:
                writer_otc = csv.DictWriter(f_otc_out, fields_otc, dialect="my_dialect")
                for line in agprior_line:
                    if line["type"] == "agprior":
                        writer.writerow(line)
                    else:
                        if line["description"] == "Абонентская плата за дополнительные услуги":
                            writer_otc.writerow(line)
