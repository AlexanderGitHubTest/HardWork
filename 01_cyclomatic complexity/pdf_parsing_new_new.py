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


from abc import ABC, abstractmethod
from collections import deque
import csv
from glob import glob
import re
import zlib


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

class TableRow(ABC):
    '''
    Класс - это строка из таблицы pdf файла
    Данный класс абстрактный, от него наследуются
    классы строк конкретных таблиц.
    Класс получает потоком элементы строки
    и вычленяет из них полные заданные строки.
    Атрибут - количество элементов строки и метод проверки строки
    задаются на уровне класса наследника.
    Также в наследнике задаются названия полей (класс возвращает строку в виде словаря)
    Кроме того класс получает при инициализации списки
    строк начала поиска таблиц и завершения поиска таблицю
    (если строка встретилась в потоке элементов строк, то, соответственно, начать или закончить поиск строк)
    Внутри реализация в виде кольцевой очереди ограниченной длины

    // ==================================================
    // АТД TableRow
    abstract class TableRow<String>

    public const int GET_ROW_OK = 1; // последняя get_row() отработала нормально
    public const int GET_ROW_NOT_FOUND = 2; // содержимое не является строкой

    // конструктор
    // постусловие: создана новая пустая строка таблицы
    public TableRow<String> TableRow(List<Int> StartText, List<Int> StopText);

     // команды

    // получить элемент строки
    // постусловие: элемент строки добавлен в строку таблицы
    public void put(String item);

    // запросы:

    // извлечение строки таблицы
    // предусловие: элементы являются строкой таблицы
    public Dict get_row();

    // дополнительные запросы:
    public int get_get_row_status(); // возвращает значение GET_ROW_*
    // ==================================================
    '''

    # Максимальная длина очереди
    # Атрибут обязательно нужно перекрывать
    # Возвращать значение int больше нуля
    @property
    @abstractmethod
    def _maxlen(self):
        pass

    # Заносим ли переданные значения в строку таблицы
    _is_working = False

    # Создание результирующего словаря
    @abstractmethod
    def _create_dict(self):
        pass

    # Проверка, что элементы являются строкой
    @abstractmethod
    def _is_table_row(self):
        pass

    _get_row_status = None

    # Публичные константы

    GET_ROW_OK = 1 # последняя get_row() отработала нормально
    GET_ROW_NOT_FOUND = 2 # содержимое не является строкой

    # Конструктор
    # постусловие: создана новая пустая строка таблицы
    def __init__(self, start_text, stop_text):
        self._start_text = start_text
        self._stop_text = stop_text
        self._row = deque(maxlen=self._maxlen)

    # Команды
    # Получить элемент строки
    # Постусловие: элемент строки добавлен в строку таблицы
    def put(self, item):
        if item in self._start_text:
            self._is_working = True
            return
        if item in self._stop_text:
            self._is_working = False
            return
        if self._is_working:
            self._row.append(item)

    # Запросы:
    # Предусловие: элементы являются строкой таблицы
    # извлечение строки таблицы
    def get_row(self):
        if (
            len(self._row) == self._maxlen
            and self._is_table_row()
        ):
            self._get_row_status = self.GET_ROW_OK
            return self._create_dict()
        self._get_row_status = self.GET_ROW_NOT_FOUND

    # Дополнительные запросы:
    def get_get_row_status(self): # возвращает значение GET_ROW_*
        return self._get_row_status


class TableAgpriorRow(TableRow):
    '''
    Строка таблицы Agprior
    '''

    @property
    def _maxlen(self):
        return 6

    def _create_dict(self):
        '''
        метод возвращает словарь
        из 6 позиций:
        phone - номер телефона
        from_date - с какой даты
        to_date - по какую дату
        service_name - название услуги
        fee - начисления по услуге
        type - тип строки - 'agprior'
        '''
        result_dict = {}
        result_dict['phone'] = self._row[0]
        result_dict['from_date'] = self._row[1]
        result_dict['to_date'] = self._row[3]
        result_dict['service_name'] = self._row[4]
        # меняем точку на запятую, чтобы excel корректно читал
        result_dict['fee'] = self._row[5].replace('.', ',')
        result_dict['type'] = 'agprior'
        return result_dict

    def _is_table_row(self):
        if self._row[4].find("ПриорОбслАгент") != -1:
            return True
        return False


class TableOneTimeChargesRow(TableRow):
    '''
    Строка таблицы One Time Charges
    '''

    @property
    def _maxlen(self):
        return 5

    def _create_dict(self):
        result_dict = {}
        result_dict['phone'] = self._row[0]
        result_dict['description'] = self._row[1]
        # меняем точку на запятую, чтобы excel корректно читал
        result_dict['charge'] = self._row[2].replace('.', ',')
        result_dict['quantity'] = self._row[4].strip()
        # меняем точку на запятую, чтобы excel корректно читал
        result_dict['summa'] = self._row[3].replace('.', ',')
        result_dict['type'] = 'one_time_charges'
        return result_dict

    def _is_table_row(self):
        '''
        Метод проверяет, что список из 5 строк является
        строкой из раздела 'Разовые начисления'.
        Проверки следующие:
        - все 5 строк не None
        - первое значение попадает под маску 'ровно 10 цифр'
        - второе значение не None
        - третье и четвертое значения типа Float (можно конвертировать)
        - пятое значение можно конвертировать в integer
        Если все проверки прошли, то возвращается True, иначе False
        '''
        for string in self._row:
            if string == None:
                return False
        if not (self._row[0].isdigit() and len(self._row[0]) == 10):
            return False
        if re.match(r"^-?\d+(?:\.\d+)$", self._row[2]) is None:
            return False
        if re.match(r"^-?\d+(?:\.\d+)$", self._row[3]) is None:
            return False
        # в количестве бывает цифра в виде "   1", поэтому функция strip
        if not self._row[4].strip().isdigit():
            return False
        return True


# Функция ищет строки Agprior или One time charge
# При нахождении строки "Детализация" прекращает работу
# (чтобы обрабатывать только приложение к счету)
def search_table_rows(list_of_strings):
    agprior_rows = TableAgpriorRow(
        ['Расшифровка начислений'],
        ['Разовые начисления']
    )
    one_time_charge_rows = TableOneTimeChargesRow(
        ['Разовые начисления'],
        ['Cкидки и надбавки', 'Перенос начислений в Единый счет']
    )
    for string in list_of_strings:

        agprior_rows.put(string)
        agp_row = agprior_rows.get_row()
        if agprior_rows.get_get_row_status() == agprior_rows.GET_ROW_OK:
            yield agp_row

        one_time_charge_rows.put(string)
        otc_row = one_time_charge_rows.get_row()
        if one_time_charge_rows.get_get_row_status() == one_time_charge_rows.GET_ROW_OK:
            yield otc_row

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
        agprior_line = search_table_rows(decoding_line)
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
