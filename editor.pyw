import copy
import json
import math
import os
import re
import tkinter as tk

from tkinter import ttk
from tkinter import filedialog
from tkinter import messagebox
from tkinter import colorchooser
from tkinter import font as tkfont


EDITOR_VERSION = "1.21"

SCREEN_WIDTH = 240
SCREEN_HEIGHT = 320

ROUND_AREA_WIDTH = 240
ROUND_AREA_HEIGHT = 240
ROUND_CENTER_X = 120
ROUND_CENTER_Y = 120
ROUND_RADIUS = 120

SCREEN_CENTER_X = ROUND_CENTER_X
SCREEN_CENTER_Y = ROUND_CENTER_Y
SCREEN_RADIUS = ROUND_RADIUS

LV_IMAGE_HEADER_SIZE = 12
LV_IMAGE_HEADER_MAGIC = 0x19
LV_COLOR_FORMAT_RGB565 = 0x12
LV_COLOR_FORMAT_ARGB8565 = 0x13

PREVIEW_FONT_FAMILY = "Roboto"

SUPPORTED_FONT_SIZES = (18, 24, 36, 48)
SUPPORTED_SCALE_FONT_SIZES = SUPPORTED_FONT_SIZES

CANPAR_NAMES = ("canpar1", "canpar2", "canpar3")
MAX_TEXT_OUTPUTS = 3

TEXT_ALIGN_LABELS = (
    "",
    "0 — left / слева",
    "1 — center / по центру",
    "2 — right / справа"
)

SUPPORTED_CANPAR_TYPES = (
    "text",
    "scale",
    "gradient_round"
)

SUPPORTED_SCALE_MODES = (
    "round_outer",
    "round_inner",
    "horizontal",
    "horizontal_top",
    "vertical",
    "vertical_left"
)

SUPPORTED_NEEDLES = ("line", "arrow")

SUPPORTED_IMAGE_IDS = {
    0: "Часы — цифры",
    1: "Минуты — цифры",
    2: "Дата — цифры",
    3: "Месяц — цифры или название",
    6: "День недели",
    7: "Год — цифры",
    13: "Аналоговая стрелка",
    100: "Статическое изображение"
}

SUPPORTED_TEXT_IDS = {
    101: "Динамическая дата",
    102: "Динамическое время",
    103: "Статический текст"
}

SUPPORTED_ACTIONS = (
    "DRIVERDOORSTATE",
    "PASSENGERDOORSTATE",
    "RLEFTDOOR",
    "RRIGHTDOOR",
    "REARFOGLAMP",
    "FRONTFOGLAMP",
    "LOWBEAM",
    "HIGHBEAM",
    "PARKINGBRAKE",
    "PositionLamp",
    "SBR1",
    "SBR2",
    "PASSAIR"
)


def deep_copy(value):
    return copy.deepcopy(value)


def safe_float(value, default=0.0):
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (ValueError, TypeError, OverflowError):
        return default


def safe_int(value, default=0):
    try:
        return int(float(value))
    except (ValueError, TypeError, OverflowError):
        return default


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def format_scale_label(value):
    numeric = safe_float(value, None)
    if numeric is None:
        return "--"

    scaled = numeric * 10.0
    if not math.isfinite(scaled):
        return "--"

    magnitude = abs(scaled)
    integer_part = math.floor(magnitude)
    if magnitude - integer_part >= 0.5:
        integer_part += 1

    tenths = -integer_part if numeric < 0 else integer_part
    if tenths == 0:
        return "0"

    sign = "-" if tenths < 0 else ""
    whole, fraction = divmod(abs(tenths), 10)
    if fraction == 0:
        return "{}{}".format(sign, whole)
    return "{}{}.{}".format(sign, whole, fraction)


def parse_color(value, default="#FFFFFF"):
    if isinstance(value, int) and not isinstance(value, bool):
        return "#{:06X}".format(value & 0xFFFFFF)
    if not isinstance(value, str):
        return default

    text = value.strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", text):
        return default
    return "#" + text.upper()


def color_to_int(value, default=0xFFFFFF):
    color = parse_color(value, None)
    return int(color[1:], 16) if color else default


def mix_color(start, end, ratio):
    start = color_to_int(start, 0x004080)
    end = color_to_int(end, 0x40C0FF)
    ratio = clamp(ratio, 0.0, 1.0)
    channels = []
    for shift in (16, 8, 0):
        a = (start >> shift) & 255
        b = (end >> shift) & 255
        channels.append(int(a + (b - a) * ratio + 0.5))
    return "#{:02X}{:02X}{:02X}".format(*channels)


def normalize_font_size(value, scale=False):
    if isinstance(value, bool):
        return 18
    numeric = safe_float(value, None)
    return int(numeric) if numeric in SUPPORTED_FONT_SIZES else 18


def make_font_size_variable(master, value=18, scale=False):
    variable = tk.IntVar(
        master=master,
        value=normalize_font_size(value, scale)
    )

    def enforce(*args):
        try:
            current = variable.get()
        except (tk.TclError, ValueError, TypeError):
            variable.set(18)
            return
        normalized = normalize_font_size(current, scale)
        if current != normalized:
            variable.set(normalized)

    variable.trace_add("write", enforce)
    return variable


def normalize_document_font_sizes(value, scale_context=False):
    if isinstance(value, dict):
        for key, child in list(value.items()):
            if key == "fontSize":
                value[key] = normalize_font_size(child)
            else:
                normalize_document_font_sizes(child)
    elif isinstance(value, list):
        for child in value:
            normalize_document_font_sizes(child)


def is_text_output(element):
    return (
        isinstance(element, dict)
        and str(element.get("type", "")).lower() == "text_output"
    )


def canonical_canpar(value):
    text = str(value or "").strip().lower()
    return text if text in CANPAR_NAMES else ""


def is_action_element(element):
    if is_text_output(element):
        return False
    return isinstance(element, dict) and (
        str(element.get("type", "")).lower() == "action"
        or bool(str(element.get("action", "") or "").strip())
    )


def canonical_action(value):
    text = str(value or "").strip()
    for action in SUPPORTED_ACTIONS:
        if action.lower() == text.lower():
            return action
    return text


def is_scale_canpar(obj):
    return isinstance(obj, dict) and (
        str(obj.get("type", "text")).lower()
        in ("scale", "gradient_round")
        or isinstance(obj.get("scale"), dict)
    )


def get_scale_config(obj):
    if not isinstance(obj, dict):
        return {}
    result = {
        key: value for key, value in obj.items()
        if key != "scale"
    }
    if isinstance(obj.get("scale"), dict):
        result.update(obj["scale"])
    return result


def is_gradient_canpar(obj):
    if not isinstance(obj, dict):
        return False
    scale = get_scale_config(obj)
    return (
        str(obj.get("type", "")).lower() == "gradient_round"
        or str(scale.get("variant", "")).lower() == "gradient_round"
    )


def make_default_scale(mode="round_outer", gradient=False):
    result = {
        "mode": mode,
        "width": 100,
        "height": 100,
        "min": 0,
        "max": 100,
        "rotation": 135,
        "angleRange": 270,
        "totalTickCount": 11,
        "majorTickEvery": 2,
        "minorTickLength": 5,
        "majorTickLength": 10,
        "tickWidth": 2,
        "lineWidth": 20 if gradient else 2,
        "fontSize": 18,
        "scaleColor": "#202020" if gradient else "#404040",
        "tickColor": "#FFFFFF",
        "labelColor": "#FFFFFF",
        "needleColor": "#FF2020",
        "needle": "line",
        "needleWidth": 3,
        "needleLength": 42,
        "rounded": True,
        "showLabels": True,
        "showTicks": not gradient
    }
    if gradient:
        result.update({
            "variant": "gradient_round",
            "startColor": "#103878",
            "endColor": "#40C8FF"
        })
    return result


SCALE_FIELDS = set(make_default_scale()) | {
    "variant", "startColor", "endColor"
}

TEXT_OUTPUT_FORBIDDEN_FIELDS = (
    SCALE_FIELDS - {"width", "fontSize"}
) | {
    "scale", "height", "action", "image", "group",
    "id", "text", "pvX", "pvY"
}


def make_default_canpar(index):
    if index == 0:
        return {
            "type": "scale",
            "x": 70, "y": 10,
            "scale": make_default_scale()
        }

    if index == 1:
        scale = make_default_scale("horizontal")
        scale.update({
            "width": 180, "height": 42,
            "max": 200,
            "needleColor": "#00FFAA",
            "tickColor": "#00FFAA",
            "labelColor": "#00FFAA",
            "needle": "arrow",
            "needleLength": 80
        })
        return {
            "type": "scale",
            "x": 30, "y": 145,
            "scale": scale
        }

    return {
        "type": "text",
        "x": 70, "y": 195,
        "fontSize": 24,
        "color": "#FFFFFF",
        "showUnit": True
    }


def make_default_json():
    return {
        "name": "CAN scales",
        "canpar": {
            name: make_default_canpar(index)
            for index, name in enumerate(CANPAR_NAMES)
        },
        "elements": [],
        "assets": []
    }


class LvglBinImage:
    RGB565_BYTEORDER = "little"

    def __init__(self, filename):
        self.filename = os.path.abspath(filename)
        self.raw = b""
        self.width = 0
        self.height = 0
        self.stride = 0
        self.color_format = 0
        self.pixels = []
        self.load()

    def load(self):
        with open(self.filename, "rb") as file:
            self.raw = file.read()

        if len(self.raw) < LV_IMAGE_HEADER_SIZE:
            raise ValueError("BIN меньше 12 байт.")

        header = self.raw[:LV_IMAGE_HEADER_SIZE]
        if header[0] != LV_IMAGE_HEADER_MAGIC:
            raise ValueError(
                "Неверный LVGL magic: 0x{:02X}.".format(header[0])
            )

        self.color_format = header[1]
        self.width = int.from_bytes(header[4:6], "little")
        self.height = int.from_bytes(header[6:8], "little")
        self.stride = int.from_bytes(header[8:10], "little")

        if self.width <= 0 or self.height <= 0:
            raise ValueError("Некорректный размер BIN.")

        if self.color_format == LV_COLOR_FORMAT_RGB565:
            self._decode(2)
        elif self.color_format == LV_COLOR_FORMAT_ARGB8565:
            self._decode(3)
        else:
            raise ValueError(
                "Неподдерживаемый color format: 0x{:02X}.".format(
                    self.color_format
                )
            )

    def _get_stride(self, bytes_per_pixel):
        minimum = self.width * bytes_per_pixel
        stride = self.stride or minimum
        if stride < minimum:
            raise ValueError(
                "Некорректный stride={}, минимум={}.".format(
                    stride, minimum
                )
            )

        required = (
            LV_IMAGE_HEADER_SIZE
            + (self.height - 1) * stride
            + minimum
        )
        if len(self.raw) < required:
            raise ValueError(
                "BIN обрезан: требуется {} байт, получено {}.".format(
                    required, len(self.raw)
                )
            )
        self.stride = stride
        return stride

    def _decode_rgb565_value(self, first, second):
        value = (
            first | (second << 8)
            if self.RGB565_BYTEORDER == "little"
            else (first << 8) | second
        )
        return (
            ((value >> 11) & 31) * 255 // 31,
            ((value >> 5) & 63) * 255 // 63,
            (value & 31) * 255 // 31
        )

    def _decode(self, bytes_per_pixel):
        stride = self._get_stride(bytes_per_pixel)
        self.pixels = []
        for y in range(self.height):
            row = []
            for x in range(self.width):
                offset = (
                    LV_IMAGE_HEADER_SIZE
                    + y * stride + x * bytes_per_pixel
                )
                if bytes_per_pixel == 3:
                    alpha = self.raw[offset]
                    offset += 1
                else:
                    alpha = None
                rgb = self._decode_rgb565_value(
                    self.raw[offset], self.raw[offset + 1]
                )
                row.append((*rgb, alpha) if alpha is not None else rgb)
            self.pixels.append(row)

    def to_ppm(self):
        result = ["P3", "{} {}".format(self.width, self.height), "255"]
        for row in self.pixels:
            values = []
            for pixel in row:
                alpha = pixel[3] if len(pixel) == 4 else 255
                values.extend(str(c * alpha // 255) for c in pixel[:3])
            result.append(" ".join(values))
        return "\n".join(result)


class DialEditor(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("SandikNavi Skin Editor " + EDITOR_VERSION)

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        width = min(1180, max(800, sw - 60))
        height = min(700, max(500, sh - 100))
        self.geometry("{}x{}+{}+{}".format(
            width, height,
            max(0, (sw - width) // 2),
            max(0, (sh - height - 50) // 2)
        ))
        self.minsize(min(1040, width), min(540, height))

        self.data = make_default_json()
        self.filename = None
        self.asset_directory = None
        self.selected_kind = None
        self.selected_key = None
        self.drag_state = None
        self.bin_cache = {}
        self.preview_images = {}
        self.text_output_buttons = []

        self._create_variables()
        self._create_menu()
        self._create_layout()
        self.refresh_all()

        families = {s.casefold() for s in tkfont.families(self)}
        if PREVIEW_FONT_FAMILY.casefold() not in families:
            self.after_idle(lambda: messagebox.showwarning(
                "Шрифт предпросмотра",
                "На компьютере не найден Roboto.\n"
                "Tkinter может использовать другой шрифт.\n"
                "Размеры текста могут отличаться от устройства.",
                parent=self
            ))

    def _create_variables(self):
        strings = {
            "name": "",
            "object_type": "text",
            "object_name": "",
            "color": "#FFFFFF",
            "scale_mode": "round_outer",
            "scale_color": "#404040",
            "tick_color": "#FFFFFF",
            "label_color": "#FFFFFF",
            "needle_color": "#FF2020",
            "start_color": "#103878",
            "end_color": "#40C8FF",
            "needle": "line",
            "element_text": "",
            "element_image": "",
            "element_group": "",
            "element_action": "",
            "new_action": SUPPORTED_ACTIONS[0],
            "text_output_source": CANPAR_NAMES[0],
            "text_width": "",
            "text_align": "",
            "preview_value1": "50",
            "preview_value2": "100",
            "preview_value3": "23",
            "x": "0", "y": "0",
            "width": "100", "height": "100",
            "min": "0", "max": "100",
            "rotation": "135", "angle_range": "270",
            "total_tick_count": "11",
            "major_tick_every": "2",
            "minor_tick_length": "5",
            "major_tick_length": "10",
            "tick_width": "2", "line_width": "2",
            "needle_width": "3", "needle_length": "42",
            "element_id": "100",
            "element_pvx": "0", "element_pvy": "0"
        }
        for name, value in strings.items():
            setattr(
                self, name + "_var",
                tk.StringVar(master=self, value=value)
            )

        for name, value in {
            "show_unit": True,
            "rounded": True,
            "show_labels": True,
            "show_ticks": True,
            "disable_grid": False
        }.items():
            setattr(
                self, name + "_var",
                tk.BooleanVar(master=self, value=value)
            )

        self.font_size_var = make_font_size_variable(self, 18)
        self.scale_font_size_var = make_font_size_variable(
            self, 18, scale=True
        )

    def _create_menu(self):
        menu = tk.Menu(self)
        file_menu = tk.Menu(menu, tearoff=False)
        for title, command in (
            ("Новый", self.new_document),
            ("Открыть JSON...", self.open_json),
            ("Сохранить", self.save_json),
            ("Сохранить как...", self.save_json_as)
        ):
            file_menu.add_command(label=title, command=command)

        file_menu.add_separator()
        file_menu.add_command(label="Открыть BIN...", command=self.open_bin)
        file_menu.add_command(
            label="Добавить BIN в assets...",
            command=self.add_bin_asset
        )
        file_menu.add_separator()
        file_menu.add_command(label="Выход", command=self.destroy)
        menu.add_cascade(label="Файл", menu=file_menu)

        tools = tk.Menu(menu, tearoff=False)
        tools.add_command(
            label="Проверить JSON", command=self.validate_document
        )
        tools.add_command(
            label="Проверить круглую область",
            command=self.check_round_area
        )
        tools.add_command(label="Показать JSON", command=self.show_json)
        menu.add_cascade(label="Инструменты", menu=tools)
        self.configure(menu=menu)

    def _create_layout(self):
        main = ttk.Frame(self, padding=6)
        main.pack(fill=tk.BOTH, expand=True)
        main.rowconfigure(0, weight=1)
        main.columnconfigure(0, minsize=240)
        main.columnconfigure(1, weight=1, minsize=270)
        main.columnconfigure(2, minsize=390)

        left = ttk.Frame(main, width=240)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        left.grid_propagate(False)

        center = ttk.Frame(main)
        center.grid(row=0, column=1, sticky="nsew", padx=6)

        right = ttk.Frame(main, width=390)
        right.grid(row=0, column=2, sticky="nsew", padx=(6, 0))
        right.grid_propagate(False)

        self._create_left_panel(left)
        self._create_center_panel(center)
        self._create_right_panel(right)

    def _create_left_panel(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        ttk.Label(
            parent, text="Объекты циферблата",
            font=("Arial", 11, "bold")
        ).grid(row=0, column=0, sticky="w", pady=(0, 5))

        notebook = ttk.Notebook(parent)
        notebook.grid(row=1, column=0, sticky="nsew")

        objects_tab = ttk.Frame(notebook, padding=5)
        add_tab = ttk.Frame(notebook, padding=5)
        notebook.add(objects_tab, text="Объекты")
        notebook.add(add_tab, text="Добавить")

        objects_tab.rowconfigure(0, weight=1)
        objects_tab.columnconfigure(0, weight=1)

        self.object_list = tk.Listbox(
            objects_tab, exportselection=False, width=1, height=8
        )
        self.object_list.grid(row=0, column=0, sticky="nsew")

        sy = ttk.Scrollbar(
            objects_tab, orient=tk.VERTICAL,
            command=self.object_list.yview
        )
        sy.grid(row=0, column=1, sticky="ns")

        sx = ttk.Scrollbar(
            objects_tab, orient=tk.HORIZONTAL,
            command=self.object_list.xview
        )
        sx.grid(row=1, column=0, sticky="ew")
        self.object_list.configure(
            yscrollcommand=sy.set, xscrollcommand=sx.set
        )
        self.object_list.bind(
            "<<ListboxSelect>>", self.on_object_selected
        )

        # Прокрутка вкладки добавления на небольших экранах.
        add_tab.rowconfigure(0, weight=1)
        add_tab.columnconfigure(0, weight=1)

        add_canvas = tk.Canvas(add_tab, highlightthickness=0, width=1)
        add_canvas.grid(row=0, column=0, sticky="nsew")
        add_scroll = ttk.Scrollbar(
            add_tab, orient=tk.VERTICAL, command=add_canvas.yview
        )
        add_scroll.grid(row=0, column=1, sticky="ns")
        add_canvas.configure(yscrollcommand=add_scroll.set)

        content = ttk.Frame(add_canvas)
        window = add_canvas.create_window(
            0, 0, anchor=tk.NW, window=content
        )
        content.bind(
            "<Configure>",
            lambda event: add_canvas.configure(
                scrollregion=add_canvas.bbox("all")
            )
        )
        add_canvas.bind(
            "<Configure>",
            lambda event: add_canvas.itemconfigure(
                window, width=max(1, event.width)
            )
        )

        ttk.Label(content, text="Основные CAN-параметры").pack(anchor=tk.W)
        can_frame = ttk.Frame(content)
        can_frame.pack(fill=tk.X, pady=(3, 6))
        for index in range(3):
            can_frame.columnconfigure(index, weight=1)
            ttk.Button(
                can_frame, text="CAN {}".format(index + 1), width=6,
                command=lambda i=index: self.add_canpar(i)
            ).grid(row=0, column=index, sticky="ew", padx=1)

        ttk.Separator(content).pack(fill=tk.X, pady=5)
        self.text_output_count_label = ttk.Label(
            content, text="Текстовые выводы: 0 / 3"
        )
        self.text_output_count_label.pack(anchor=tk.W)

        for index in range(3):
            button = ttk.Button(
                content,
                text="Текстовый вывод {} → canpar{}".format(
                    index + 1, index + 1
                ),
                command=lambda i=index: self.add_text_output(i)
            )
            button.pack(fill=tk.X, pady=2)
            self.text_output_buttons.append(button)

        ttk.Label(
            content,
            text="Всего до 3 выводов. Источник можно изменить.",
            wraplength=185
        ).pack(anchor=tk.W, pady=(2, 5))

        ttk.Separator(content).pack(fill=tk.X, pady=5)
        ttk.Label(content, text="Элементы custom_face").pack(anchor=tk.W)

        for title, element_id, kind in (
            ("Статический текст", 103, "static_text"),
            ("Динамическая дата", 101, "date"),
            ("Динамическое время", 102, "time"),
            ("Статическое изображение", 100, "image")
        ):
            ttk.Button(
                content, text=title,
                command=lambda i=element_id, k=kind: self.add_element(i, k)
            ).pack(fill=tk.X, pady=2)

        ttk.Separator(content).pack(fill=tk.X, pady=6)
        ttk.Label(content, text="Action-индикатор").pack(anchor=tk.W)
        ttk.Combobox(
            content, textvariable=self.new_action_var,
            values=SUPPORTED_ACTIONS, state="readonly", width=18
        ).pack(fill=tk.X, pady=3)
        ttk.Button(
            content, text="Добавить индикатор",
            command=self.add_action_indicator
        ).pack(fill=tk.X, pady=2)

        bottom = ttk.Frame(parent)
        bottom.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        ttk.Label(bottom, text="Имя циферблата").pack(anchor=tk.W)
        name_row = ttk.Frame(bottom)
        name_row.pack(fill=tk.X, pady=3)
        ttk.Entry(
            name_row, textvariable=self.name_var, width=12
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(
            name_row, text="OK", width=4, command=self.apply_name
        ).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(
            bottom, text="Удалить выбранный объект",
            command=self.delete_selected
        ).pack(fill=tk.X, pady=(4, 0))

    def _create_center_panel(self, parent):
        ttk.Label(
            parent, text="Предпросмотр 240×320",
            font=("Arial", 11, "bold")
        ).pack(anchor=tk.W)
        ttk.Checkbutton(
            parent, text="Отключить сетку",
            variable=self.disable_grid_var, command=self.draw_preview
        ).pack(anchor=tk.W, pady=(4, 0))

        holder = ttk.Frame(parent)
        holder.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(
            holder, width=SCREEN_WIDTH, height=SCREEN_HEIGHT,
            background="#000000", highlightthickness=1,
            highlightbackground="#777777", takefocus=True
        )
        self.canvas.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        for sequence, command in (
            ("<Button-1>", self.canvas_mouse_down),
            ("<B1-Motion>", self.canvas_mouse_move),
            ("<ButtonRelease-1>", self.canvas_mouse_up),
            ("<Double-Button-1>", self.canvas_double_click)
        ):
            self.canvas.bind(sequence, command)

        for sequence in ("<Up>", "<Down>", "<Left>", "<Right>"):
            self.bind(sequence, self.move_selected_with_keyboard, add="+")

        test = ttk.LabelFrame(parent, text="Тестовые значения")
        test.pack(fill=tk.X, pady=(5, 0))
        for column, variable in enumerate((
            self.preview_value1_var,
            self.preview_value2_var,
            self.preview_value3_var
        )):
            test.columnconfigure(column, weight=1)
            ttk.Label(
                test, text=CANPAR_NAMES[column]
            ).grid(row=0, column=column, padx=4)
            entry = ttk.Entry(test, textvariable=variable, width=7)
            entry.grid(
                row=1, column=column, sticky="ew", padx=4, pady=3
            )
            entry.bind("<Return>", lambda event: self.draw_preview())

        ttk.Button(
            test, text="Обновить предпросмотр", command=self.draw_preview
        ).grid(
            row=2, column=0, columnspan=3,
            sticky="ew", padx=4, pady=(1, 4)
        )
        ttk.Label(
            parent,
            text=(
                "Жёлтая рамка — выбранный объект. Сетка: 20×20.\n"
                "ЛКМ — перетаскивание; стрелки — сдвиг на 1 px.\n"
                "Текстовые выводы используют те же тестовые значения.\n"
                "Круглая область: верхние 240×240."
            ),
            wraplength=290, justify=tk.LEFT
        ).pack(anchor=tk.W, pady=5)

    def _create_right_panel(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        ttk.Label(
            parent, text="Свойства", font=("Arial", 11, "bold")
        ).grid(row=0, column=0, sticky="w", pady=(0, 5))

        holder = ttk.Frame(parent)
        holder.grid(row=1, column=0, sticky="nsew")
        holder.columnconfigure(0, weight=1)
        holder.rowconfigure(0, weight=1)

        background = (
            ttk.Style(self).lookup("TFrame", "background")
            or self.cget("background")
        )
        self.properties_canvas = tk.Canvas(
            holder, width=1, height=1,
            background=background, highlightthickness=0
        )
        self.properties_canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(
            holder, orient=tk.VERTICAL,
            command=self.properties_canvas.yview
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.properties_canvas.configure(yscrollcommand=scrollbar.set)

        self.properties_frame = ttk.Frame(
            self.properties_canvas, padding=(0, 0, 6, 0)
        )
        self._properties_window = self.properties_canvas.create_window(
            0, 0, anchor=tk.NW, window=self.properties_frame
        )
        self.properties_frame.bind(
            "<Configure>", self._update_properties_scrollregion
        )
        self.properties_canvas.bind(
            "<Configure>", self._resize_properties_content
        )

        footer = ttk.Frame(parent)
        footer.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        self.apply_properties_button = ttk.Button(
            footer, text="Применить свойства", command=self.apply_properties
        )
        self.apply_properties_button.pack(fill=tk.X, pady=(0, 3))
        self.center_properties_button = ttk.Button(
            footer, text="Центрировать объект", command=self.center_selected
        )
        self.center_properties_button.pack(fill=tk.X)

        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.bind(sequence, self._scroll_properties_with_mouse, add="+")

    def _update_properties_scrollregion(self, event=None):
        bbox = self.properties_canvas.bbox("all")
        if bbox:
            self.properties_canvas.configure(scrollregion=bbox)

    def _resize_properties_content(self, event):
        self.properties_canvas.itemconfigure(
            self._properties_window, width=max(1, event.width)
        )

    def _scroll_properties_with_mouse(self, event):
        widget = self.winfo_containing(event.x_root, event.y_root)
        if widget is None or widget.winfo_class() == "TCombobox":
            return None

        current = widget
        while current is not None:
            if current is self.properties_canvas:
                break
            current = getattr(current, "master", None)
        else:
            return None

        first, last = self.properties_canvas.yview()
        if first <= 0 and last >= 1:
            return None

        number = getattr(event, "num", None)
        delta = getattr(event, "delta", 0)
        if number == 4:
            steps = -3
        elif number == 5:
            steps = 3
        elif delta:
            steps = max(1, abs(int(delta / 120)))
            if delta > 0:
                steps = -steps
        else:
            return None

        self.properties_canvas.yview_scroll(steps, "units")
        return "break"

    def count_text_outputs(self):
        return sum(
            1 for element in self.data.get("elements", [])
            if is_text_output(element)
        )

    def refresh_all(self):
        normalize_document_font_sizes(self.data)
        self.name_var.set(self.data.get("name", "Custom face"))
        self.refresh_object_list()
        self.draw_preview()
        if self.get_selected_object() is not None:
            self.load_property_variables()
        self.show_properties()

    def refresh_object_list(self):
        self.object_list.delete(0, tk.END)
        for name, obj in self.data.get("canpar", {}).items():
            if not isinstance(obj, dict):
                continue
            if is_gradient_canpar(obj):
                kind = "gradient_round"
            elif is_scale_canpar(obj):
                kind = "scale:" + str(
                    get_scale_config(obj).get("mode", "round_outer")
                )
            else:
                kind = "text"
            self.object_list.insert(
                tk.END, "CAN|{}|{} [{}]".format(name, name, kind)
            )

        output_number = 0
        for index, element in enumerate(self.data.get("elements", [])):
            if not isinstance(element, dict):
                title = "Некорректный элемент"
            elif is_text_output(element):
                output_number += 1
                source = canonical_canpar(element.get("canpar"))
                title = "Текстовый вывод {} → {}".format(
                    output_number, source or "неверный источник"
                )
            elif is_action_element(element):
                title = "Индикатор: " + canonical_action(
                    element.get("action")
                )
            else:
                element_id = safe_int(element.get("id", 100), 100)
                title = SUPPORTED_TEXT_IDS.get(
                    element_id,
                    SUPPORTED_IMAGE_IDS.get(
                        element_id, "Изображение id={}".format(element_id)
                    )
                )
                if element.get("text"):
                    title += ": " + str(element["text"])

            if (
                isinstance(element, dict)
                and not is_text_output(element)
                and element.get("image")
            ):
                title += " — " + str(element["image"]).replace(
                    "\\", "/"
                ).split("/")[-1]

            self.object_list.insert(
                tk.END, "ELEMENT|{}|{}".format(index, title)
            )

        count = self.count_text_outputs()
        self.text_output_count_label.configure(
            text="Текстовые выводы: {} / {}".format(
                count, MAX_TEXT_OUTPUTS
            )
        )
        for button in self.text_output_buttons:
            button.configure(
                state=tk.NORMAL if count < MAX_TEXT_OUTPUTS else tk.DISABLED
            )
        self._mark_list_selection()

    def _mark_list_selection(self):
        self.object_list.selection_clear(0, tk.END)
        if self.selected_kind is None:
            return
        prefix = "CAN" if self.selected_kind == "canpar" else "ELEMENT"
        for index in range(self.object_list.size()):
            parts = self.object_list.get(index).split("|", 2)
            if (
                len(parts) >= 2 and parts[0] == prefix
                and parts[1] == str(self.selected_key)
            ):
                self.object_list.selection_set(index)
                self.object_list.activate(index)
                break

    def get_selected_object(self):
        if self.selected_kind == "canpar":
            return self.data.get("canpar", {}).get(self.selected_key)
        if self.selected_kind == "element":
            index = safe_int(self.selected_key, -1)
            elements = self.data.get("elements", [])
            if 0 <= index < len(elements):
                return elements[index]
        return None

    def select_object(self, kind, key):
        self.selected_kind = kind
        self.selected_key = str(key)
        self._mark_list_selection()
        self.load_property_variables()
        self.show_properties()
        self.draw_preview()

    def on_object_selected(self, event=None):
        selected = self.object_list.curselection()
        if not selected:
            return
        parts = self.object_list.get(selected[0]).split("|", 2)
        if len(parts) >= 2:
            self.select_object(
                "canpar" if parts[0] == "CAN" else "element", parts[1]
            )

    def show_properties(self):
        for child in self.properties_frame.winfo_children():
            child.destroy()

        obj = self.get_selected_object()
        enabled = isinstance(obj, dict)
        for button in (
            self.apply_properties_button, self.center_properties_button
        ):
            button.configure(state=tk.NORMAL if enabled else tk.DISABLED)

        if not enabled:
            ttk.Label(
                self.properties_frame,
                text="Выберите объект в списке или на предпросмотре.",
                wraplength=340
            ).pack(anchor=tk.W)
        elif self.selected_kind == "canpar":
            self.show_canpar_properties(obj)
        elif is_text_output(obj):
            self.show_text_output_properties(obj)
        else:
            self.show_element_properties(obj)

        self.properties_canvas.yview_moveto(0)
        self.properties_canvas.after_idle(
            self._update_properties_scrollregion
        )

    def add_property(self, title, variable):
        row = ttk.Frame(self.properties_frame)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text=title, width=22).pack(side=tk.LEFT)
        if variable is self.font_size_var or variable is self.scale_font_size_var:
            widget = ttk.Combobox(
                row, textvariable=variable,
                values=SUPPORTED_FONT_SIZES,
                state="readonly", width=10
            )
        else:
            widget = ttk.Entry(row, textvariable=variable, width=14)
        widget.pack(side=tk.RIGHT, fill=tk.X, expand=True)
        return widget

    def add_combo(self, title, variable, values):
        row = ttk.Frame(self.properties_frame)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text=title, width=22).pack(side=tk.LEFT)
        widget = ttk.Combobox(
            row, textvariable=variable,
            values=values, state="readonly", width=14
        )
        widget.pack(side=tk.RIGHT, fill=tk.X, expand=True)
        return widget

    def add_color_property(self, title, variable):
        row = ttk.Frame(self.properties_frame)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text=title, width=22).pack(side=tk.LEFT)
        ttk.Entry(
            row, textvariable=variable, width=10
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(
            row, text="...", width=3,
            command=lambda: self.choose_color(variable)
        ).pack(side=tk.RIGHT, padx=(3, 0))

    def choose_color(self, variable):
        result = colorchooser.askcolor(
            color=parse_color(variable.get()), parent=self
        )
        if result and result[1]:
            variable.set(result[1].upper())

    def add_text_properties(self):
        self.add_property("Размер шрифта", self.font_size_var)
        self.add_color_property("Цвет", self.color_var)
        ttk.Checkbutton(
            self.properties_frame, text="Показывать единицу",
            variable=self.show_unit_var
        ).pack(anchor=tk.W, pady=4)
        ttk.Separator(self.properties_frame).pack(fill=tk.X, pady=7)
        self.add_property("Ширина текста, px", self.text_width_var)
        self.add_combo(
            "Выравнивание", self.text_align_var, TEXT_ALIGN_LABELS
        )
        ttk.Label(
            self.properties_frame,
            text=(
                "Пустая ширина — автоматически по содержимому.\n"
                "Ширина: целое число 1…32767 пикселей.\n"
                "Пустое выравнивание — слева.\n"
                "X и Y — левый верхний угол области.\n"
                "Для выравнивания внутри области задайте ширину.\n"
                "Длинное значение обрезается без переноса."
            ),
            wraplength=350, justify=tk.LEFT
        ).pack(anchor=tk.W, pady=6)

    def show_text_output_properties(self, obj):
        ttk.Label(
            self.properties_frame,
            text="Текстовый вывод",
            font=("Arial", 11, "bold")
        ).pack(anchor=tk.W, pady=(0, 5))
        self.add_combo(
            "Источник значения",
            self.text_output_source_var,
            CANPAR_NAMES
        )
        self.add_property("X", self.x_var)
        self.add_property("Y", self.y_var)
        ttk.Label(
            self.properties_frame,
            text=(
                "Независимый текстовый дубль выбранного canpar.\n"
                "Работает и без основного объекта canpar в JSON.\n"
                "Шкалы не поддерживаются. Всего до 3 выводов."
            ),
            wraplength=350, justify=tk.LEFT
        ).pack(anchor=tk.W, pady=6)
        self.add_text_properties()

    def show_canpar_properties(self, obj):
        self.add_property("Имя", self.object_name_var)
        combo = self.add_combo(
            "Тип", self.object_type_var, SUPPORTED_CANPAR_TYPES
        )
        combo.bind("<<ComboboxSelected>>", self.on_canpar_type_changed)
        self.add_property("X", self.x_var)
        self.add_property("Y", self.y_var)
        ttk.Separator(self.properties_frame).pack(fill=tk.X, pady=7)
        kind = self.object_type_var.get()
        if kind in ("scale", "gradient_round"):
            self.add_scale_properties(kind == "gradient_round")
        else:
            self.add_text_properties()

    def on_canpar_type_changed(self, event=None):
        obj = self.get_selected_object()
        if not isinstance(obj, dict):
            return
        if (
            self.object_type_var.get() == "gradient_round"
            and not is_gradient_canpar(obj)
        ):
            self.line_width_var.set("20")
            self.scale_font_size_var.set(18)
            self.scale_mode_var.set("round_outer")
            self.show_ticks_var.set(False)
        self.show_properties()

    def add_scale_properties(self, gradient=False):
        self.add_property("Ширина объекта", self.width_var)
        self.add_property("Высота объекта", self.height_var)
        if gradient:
            ttk.Label(
                self.properties_frame,
                text=(
                    "Круговая шкала без стрелки.\n"
                    "Подписи — на средней линии дуги.\n"
                    "Градиент привязан к диапазону min..max."
                ),
                wraplength=350
            ).pack(anchor=tk.W, pady=5)
        else:
            self.add_combo(
                "Режим", self.scale_mode_var, SUPPORTED_SCALE_MODES
            )

        for title, variable in (
            ("Минимум", self.min_var),
            ("Максимум", self.max_var),
            ("Поворот", self.rotation_var),
            ("Диапазон угла", self.angle_range_var),
            ("Всего делений", self.total_tick_count_var),
            ("Главное через N", self.major_tick_every_var),
            ("Длина малых делений", self.minor_tick_length_var),
            ("Длина больших делений", self.major_tick_length_var),
            ("Толщина делений", self.tick_width_var),
            ("Толщина дуги, px" if gradient else "Толщина линии",
             self.line_width_var),
            ("Шрифт шкалы", self.scale_font_size_var)
        ):
            self.add_property(title, variable)

        if gradient:
            self.add_color_property("Начальный цвет", self.start_color_var)
            self.add_color_property("Конечный цвет", self.end_color_var)
        self.add_color_property(
            "Незаполненная дуга" if gradient else "Цвет шкалы",
            self.scale_color_var
        )
        self.add_color_property("Цвет делений", self.tick_color_var)
        self.add_color_property("Цвет подписей", self.label_color_var)
        if not gradient:
            self.add_color_property("Цвет стрелки", self.needle_color_var)
            self.add_combo("Тип стрелки", self.needle_var, SUPPORTED_NEEDLES)
            self.add_property("Толщина стрелки", self.needle_width_var)
            self.add_property("Длина стрелки", self.needle_length_var)

        for title, variable in (
            ("Закруглённые линии", self.rounded_var),
            ("Показывать подписи", self.show_labels_var),
            ("Показывать деления", self.show_ticks_var)
        ):
            ttk.Checkbutton(
                self.properties_frame, text=title, variable=variable
            ).pack(anchor=tk.W, pady=2)

    def show_element_properties(self, obj):
        action = is_action_element(obj)
        element_id = safe_int(obj.get("id", 100), 100)
        if action:
            self.add_combo(
                "Action", self.element_action_var, SUPPORTED_ACTIONS
            )
            ttk.Label(
                self.properties_frame,
                text="В предпросмотре индикатор всегда виден.",
                wraplength=350
            ).pack(anchor=tk.W, pady=5)
        else:
            self.add_property("ID", self.element_id_var)

        for title, variable in (
            ("X", self.x_var), ("Y", self.y_var),
            ("Pivot X", self.element_pvx_var),
            ("Pivot Y", self.element_pvy_var)
        ):
            self.add_property(title, variable)

        if not action and element_id in SUPPORTED_TEXT_IDS:
            self.add_property("Текст", self.element_text_var)
            self.add_property("Размер шрифта", self.font_size_var)
            self.add_color_property("Цвет", self.color_var)
        else:
            self.add_property("BIN/image", self.element_image_var)
            if not action:
                self.add_property("Группа BIN через ;", self.element_group_var)
            ttk.Button(
                self.properties_frame, text="Выбрать BIN...",
                command=self.select_bin_for_element
            ).pack(fill=tk.X, pady=3)
            ttk.Button(
                self.properties_frame, text="Открыть BIN",
                command=self.open_selected_bin
            ).pack(fill=tk.X, pady=3)

    def load_text_property_variables(self, obj):
        self.font_size_var.set(normalize_font_size(obj.get("fontSize", 18)))
        self.color_var.set(parse_color(obj.get("color")))
        self.show_unit_var.set(bool(obj.get("showUnit", True)))
        self.text_width_var.set(
            str(obj["width"]) if "width" in obj else ""
        )
        align = obj.get("align")
        if type(align) is int and align in (0, 1, 2):
            self.text_align_var.set(TEXT_ALIGN_LABELS[align + 1])
        else:
            self.text_align_var.set(
                str(align) if "align" in obj else ""
            )

    def load_property_variables(self):
        obj = self.get_selected_object()
        if not isinstance(obj, dict):
            return
        self.x_var.set(str(safe_int(obj.get("x", 0))))
        self.y_var.set(str(safe_int(obj.get("y", 0))))

        if self.selected_kind == "canpar":
            gradient = is_gradient_canpar(obj)
            scale_object = is_scale_canpar(obj)
            self.object_name_var.set(self.selected_key)
            self.object_type_var.set(
                "gradient_round" if gradient
                else "scale" if scale_object else "text"
            )
            self.load_text_property_variables(obj)
            if scale_object:
                self.text_width_var.set("")
                self.text_align_var.set("")

            scale = make_default_scale(gradient=gradient)
            if scale_object:
                scale.update(get_scale_config(obj))

            for key, variable in (
                ("width", self.width_var),
                ("height", self.height_var),
                ("min", self.min_var),
                ("max", self.max_var),
                ("rotation", self.rotation_var),
                ("angleRange", self.angle_range_var),
                ("totalTickCount", self.total_tick_count_var),
                ("majorTickEvery", self.major_tick_every_var),
                ("minorTickLength", self.minor_tick_length_var),
                ("majorTickLength", self.major_tick_length_var),
                ("tickWidth", self.tick_width_var),
                ("lineWidth", self.line_width_var),
                ("needleWidth", self.needle_width_var),
                ("needleLength", self.needle_length_var)
            ):
                variable.set(str(safe_int(scale.get(key, 0))))

            self.scale_font_size_var.set(
                normalize_font_size(scale.get("fontSize", 18), True)
            )
            self.scale_mode_var.set(scale.get("mode", "round_outer"))
            self.needle_var.set(scale.get("needle", "line"))
            for key, variable, default in (
                ("scaleColor", self.scale_color_var, "#404040"),
                ("tickColor", self.tick_color_var, "#FFFFFF"),
                ("labelColor", self.label_color_var, "#FFFFFF"),
                ("needleColor", self.needle_color_var, "#FF2020"),
                ("startColor", self.start_color_var, "#103878"),
                ("endColor", self.end_color_var, "#40C8FF")
            ):
                variable.set(parse_color(scale.get(key), default))
            for key, variable in (
                ("rounded", self.rounded_var),
                ("showLabels", self.show_labels_var),
                ("showTicks", self.show_ticks_var)
            ):
                variable.set(bool(scale.get(key, True)))
            return

        if is_text_output(obj):
            self.text_output_source_var.set(
                canonical_canpar(obj.get("canpar"))
                or str(obj.get("canpar", ""))
            )
            self.load_text_property_variables(obj)
            return

        self.element_id_var.set(str(safe_int(obj.get("id", 100), 100)))
        self.element_text_var.set(str(obj.get("text", "") or ""))
        self.element_image_var.set(str(obj.get("image", "") or ""))
        self.element_pvx_var.set(str(safe_int(obj.get("pvX", 0))))
        self.element_pvy_var.set(str(safe_int(obj.get("pvY", 0))))
        self.element_group_var.set(self.group_to_text(obj.get("group", [])))
        self.element_action_var.set(canonical_action(obj.get("action")))
        self.font_size_var.set(normalize_font_size(obj.get("fontSize", 18)))
        self.color_var.set(parse_color(obj.get("color")))

    def _read_canpar_text_layout_form(self):
        result = {}
        text = self.text_width_var.get().strip()
        if text:
            if not re.fullmatch(r"[0-9]+", text):
                raise ValueError(
                    "Ширина текста: целое число 1…32767 или пустое поле."
                )
            width = int(text)
            if not 1 <= width <= 32767:
                raise ValueError("Ширина текста должна быть 1…32767.")
            result["width"] = width

        text = self.text_align_var.get().strip()
        values = {
            TEXT_ALIGN_LABELS[1]: 0,
            TEXT_ALIGN_LABELS[2]: 1,
            TEXT_ALIGN_LABELS[3]: 2,
            "0": 0, "1": 1, "2": 2
        }
        if text:
            if text not in values:
                raise ValueError("Выравнивание: 0, 1 или 2.")
            result["align"] = values[text]
        return result

    def read_text_form(self):
        result = self._read_canpar_text_layout_form()
        result.update({
            "fontSize": normalize_font_size(self.font_size_var.get()),
            "color": parse_color(self.color_var.get()),
            "showUnit": bool(self.show_unit_var.get())
        })
        return result

    def read_scale_form(self, obj, gradient):
        scale = get_scale_config(obj) if is_scale_canpar(obj) else {}
        for field in (
            "x", "y", "type", "color", "showUnit", "align", "scale"
        ):
            scale.pop(field, None)

        scale["width"] = max(
            6 if gradient else 1, safe_int(self.width_var.get(), 100)
        )
        scale["height"] = max(
            6 if gradient else 1, safe_int(self.height_var.get(), 100)
        )
        scale["min"] = safe_int(self.min_var.get(), 0)
        scale["max"] = safe_int(self.max_var.get(), 100)
        if scale["max"] <= scale["min"]:
            raise ValueError("Максимум должен быть больше минимума.")

        scale["rotation"] = safe_int(self.rotation_var.get(), 135)
        scale["angleRange"] = safe_int(self.angle_range_var.get(), 270)
        if gradient and not 1 <= scale["angleRange"] <= 360:
            raise ValueError("Диапазон угла градиентной шкалы: 1..360.")

        for field, variable, default, minimum in (
            ("totalTickCount", self.total_tick_count_var, 11, 2),
            ("majorTickEvery", self.major_tick_every_var, 2, 1),
            ("minorTickLength", self.minor_tick_length_var, 5, 0),
            ("majorTickLength", self.major_tick_length_var, 10, 0),
            ("tickWidth", self.tick_width_var, 2, 0),
            ("lineWidth", self.line_width_var, 20 if gradient else 2, 1)
        ):
            scale[field] = max(minimum, safe_int(variable.get(), default))

        if gradient:
            limit = (min(scale["width"], scale["height"]) - 2) // 2
            if scale["lineWidth"] > limit:
                raise ValueError(
                    "Максимальная толщина дуги для этого размера: {} px."
                    .format(limit)
                )

        scale["fontSize"] = normalize_font_size(
            self.scale_font_size_var.get(), True
        )
        for field, variable, default in (
            ("scaleColor", self.scale_color_var,
             "#202020" if gradient else "#404040"),
            ("tickColor", self.tick_color_var, "#FFFFFF"),
            ("labelColor", self.label_color_var, "#FFFFFF")
        ):
            scale[field] = parse_color(variable.get(), default)

        for field, variable in (
            ("rounded", self.rounded_var),
            ("showLabels", self.show_labels_var),
            ("showTicks", self.show_ticks_var)
        ):
            scale[field] = bool(variable.get())

        if gradient:
            scale.update({
                "variant": "gradient_round",
                "mode": "round_outer",
                "rotation": scale["rotation"] % 360,
                "startColor": parse_color(
                    self.start_color_var.get(), "#103878"
                ),
                "endColor": parse_color(
                    self.end_color_var.get(), "#40C8FF"
                )
            })
            for field in (
                "needle", "needleColor", "needleWidth", "needleLength"
            ):
                scale.pop(field, None)
        else:
            for field in ("variant", "startColor", "endColor"):
                scale.pop(field, None)
            scale.update({
                "mode": self.scale_mode_var.get(),
                "needle": self.needle_var.get(),
                "needleColor": parse_color(
                    self.needle_color_var.get(), "#FF2020"
                ),
                "needleWidth": max(
                    1, safe_int(self.needle_width_var.get(), 3)
                ),
                "needleLength": max(
                    1, safe_int(self.needle_length_var.get(), 42)
                )
            })
        return scale

    def apply_properties(self):
        obj = self.get_selected_object()
        if not isinstance(obj, dict):
            return

        try:
            updated = deep_copy(obj)
            updated["x"] = safe_int(self.x_var.get())
            updated["y"] = safe_int(self.y_var.get())

            if self.selected_kind == "canpar":
                old_name = self.selected_key
                new_name = self.object_name_var.get().strip() or old_name
                if new_name not in CANPAR_NAMES:
                    raise ValueError("Имя CAN: canpar1, canpar2 или canpar3.")
                canpar = self.data.setdefault("canpar", {})
                if new_name != old_name and new_name in canpar:
                    raise ValueError("Объект с таким именем уже существует.")

                kind = self.object_type_var.get()
                if kind not in SUPPORTED_CANPAR_TYPES:
                    raise ValueError("Неизвестный тип CAN.")

                if kind in ("scale", "gradient_round"):
                    scale = self.read_scale_form(
                        obj, kind == "gradient_round"
                    )
                    for field in SCALE_FIELDS | {"color", "showUnit", "align"}:
                        updated.pop(field, None)
                    updated["type"] = "scale"
                    updated["scale"] = scale
                else:
                    text = self.read_text_form()
                    for field in SCALE_FIELDS | {"scale", "align"}:
                        updated.pop(field, None)
                    updated["type"] = "text"
                    updated.update(text)

                if new_name != old_name:
                    canpar.pop(old_name, None)
                canpar[new_name] = updated
                self.selected_key = new_name

            elif is_text_output(obj):
                source = canonical_canpar(self.text_output_source_var.get())
                if not source:
                    raise ValueError("Выберите источник canpar1, canpar2 или canpar3.")
                if self.count_text_outputs() > MAX_TEXT_OUTPUTS:
                    raise ValueError(
                        "В документе больше 3 текстовых выводов. "
                        "Удалите лишние объекты."
                    )

                text = self.read_text_form()
                for field in TEXT_OUTPUT_FORBIDDEN_FIELDS | {"width", "align"}:
                    updated.pop(field, None)
                updated["type"] = "text_output"
                updated["canpar"] = source
                updated.update(text)
                self.data["elements"][int(self.selected_key)] = updated

            else:
                index = int(self.selected_key)
                updated["pvX"] = safe_int(self.element_pvx_var.get())
                updated["pvY"] = safe_int(self.element_pvy_var.get())

                if is_action_element(obj):
                    action = canonical_action(self.element_action_var.get())
                    if action not in SUPPORTED_ACTIONS:
                        raise ValueError("Выберите поддерживаемый action.")
                    for other_index, element in enumerate(
                        self.data.get("elements", [])
                    ):
                        if (
                            other_index != index
                            and is_action_element(element)
                            and canonical_action(element.get("action")) == action
                        ):
                            raise ValueError(
                                "Индикатор {} уже существует.".format(action)
                            )
                    updated["type"] = "action"
                    updated["action"] = action
                    updated["image"] = self.element_image_var.get().strip()
                    for field in ("id", "text", "group", "fontSize", "color"):
                        updated.pop(field, None)
                else:
                    element_id = safe_int(self.element_id_var.get(), 100)
                    updated["id"] = element_id
                    updated.pop("action", None)
                    if element_id in SUPPORTED_TEXT_IDS:
                        updated["type"] = (
                            "text" if element_id == 103 else "dynamic_text"
                        )
                        updated["text"] = self.element_text_var.get()
                        updated["fontSize"] = normalize_font_size(
                            self.font_size_var.get()
                        )
                        updated["color"] = parse_color(self.color_var.get())
                        updated.pop("image", None)
                        updated.pop("group", None)
                    else:
                        updated["type"] = "image"
                        updated["image"] = self.element_image_var.get().strip()
                        group = self.text_to_group(self.element_group_var.get())
                        if group:
                            updated["group"] = group
                        else:
                            updated.pop("group", None)
                        updated.pop("text", None)
                self.data["elements"][index] = updated

        except (ValueError, TypeError, tk.TclError) as error:
            messagebox.showerror("Свойства", str(error), parent=self)
            return

        self.refresh_all()

    def add_canpar(self, index):
        name = CANPAR_NAMES[index]
        canpar = self.data.setdefault("canpar", {})
        if name not in canpar:
            canpar[name] = make_default_canpar(index)
            self.refresh_all()
        self.select_object("canpar", name)

    def add_text_output(self, source_index):
        if self.count_text_outputs() >= MAX_TEXT_OUTPUTS:
            messagebox.showwarning(
                "Текстовые выводы",
                "Разрешено максимум 3 текстовых вывода на циферблат.",
                parent=self
            )
            return

        count = self.count_text_outputs()
        elements = self.data.setdefault("elements", [])
        elements.append({
            "type": "text_output",
            "canpar": CANPAR_NAMES[source_index],
            "x": 20,
            "y": 245 + count * 24,
            "width": 200,
            "align": 1,
            "fontSize": 18,
            "color": ("#FFFF00", "#00FFFF", "#FF80FF")[count],
            "showUnit": True
        })
        self.refresh_all()
        self.select_object("element", len(elements) - 1)

    def add_element(self, element_id, kind):
        elements = self.data.setdefault("elements", [])
        if element_id in SUPPORTED_TEXT_IDS:
            element = {
                "id": element_id,
                "type": "text" if element_id == 103 else "dynamic_text",
                "x": 70, "y": 100,
                "fontSize": 36 if element_id == 102 else 18,
                "color": "#FFFFFF",
                "text": {101: "Дата", 102: "Время", 103: "TEXT"}[element_id]
            }
        else:
            element = {
                "id": element_id, "type": "image",
                "x": 70, "y": 70,
                "pvX": 0, "pvY": 0,
                "image": "", "group": []
            }
        elements.append(element)
        self.refresh_all()
        self.select_object("element", len(elements) - 1)

    def add_action_indicator(self):
        action = canonical_action(self.new_action_var.get())
        elements = self.data.setdefault("elements", [])
        for index, element in enumerate(elements):
            if (
                is_action_element(element)
                and canonical_action(element.get("action")) == action
            ):
                self.select_object("element", index)
                messagebox.showinfo(
                    "Индикатор", "Этот индикатор уже существует.", parent=self
                )
                return
        elements.append({
            "type": "action", "action": action,
            "image": "", "x": 20, "y": 20,
            "pvX": 0, "pvY": 0
        })
        self.refresh_all()
        self.select_object("element", len(elements) - 1)

    def delete_selected(self):
        if self.get_selected_object() is None:
            return
        if not messagebox.askyesno(
            "Удаление", "Удалить выбранный объект?", parent=self
        ):
            return

        if self.selected_kind == "canpar":
            self.data.get("canpar", {}).pop(self.selected_key, None)
        else:
            index = safe_int(self.selected_key, -1)
            if 0 <= index < len(self.data.get("elements", [])):
                self.data["elements"].pop(index)
        self.selected_kind = None
        self.selected_key = None
        self.drag_state = None
        self.refresh_all()

    def _get_canpar_text_layout(self, obj):
        width = obj.get("width")
        if type(width) is not int or not 1 <= width <= 32767:
            width = None
        align = obj.get("align")
        if type(align) is not int or align not in (0, 1, 2):
            align = 0
        return width, align

    def preview_text(self, name):
        variables = dict(zip(CANPAR_NAMES, (
            self.preview_value1_var,
            self.preview_value2_var,
            self.preview_value3_var
        )))
        variable = variables.get(name)
        return variable.get() if variable else "--"

    def _prepare_canpar_preview_text(self, name, obj):
        # Прошивка ограничивает исходное значение буфером 128 байт.
        raw = self.preview_text(name).encode("utf-8")[:127]
        text = raw.decode("utf-8", errors="ignore")
        if not obj.get("showUnit", True):
            parts = text.strip(" \t\r\n").split()
            text = parts[0] if parts else ""
        return re.sub(
            r"^([ \t\r\n]*[+-]?[0-9]+)\.0+(?![0-9])",
            r"\1", text
        )

    def preview_font(self, size):
        return (PREVIEW_FONT_FAMILY, -normalize_font_size(size), "normal")

    def _get_canpar_text_bounds(self, name, obj):
        x = safe_int(obj.get("x", 0))
        y = safe_int(obj.get("y", 0))
        font = tkfont.Font(
            root=self, font=self.preview_font(obj.get("fontSize", 18))
        )
        lines = self._prepare_canpar_preview_text(name, obj).split("\n")
        width, _ = self._get_canpar_text_layout(obj)
        if width is None:
            width = max(1, max(font.measure(line) for line in lines))
        height = max(1, font.metrics("linespace") * len(lines))
        return x, y, width, height

    def _clip_preview_text_line(self, text, font, width, align):
        text_width = font.measure(text)
        offset = (
            (width - text_width) / 2.0 if align == 1
            else width - text_width if align == 2 else 0.0
        )
        if text_width <= width:
            return text, offset

        first = None
        last = None
        first_position = 0
        for index in range(len(text)):
            left = font.measure(text[:index])
            right = font.measure(text[:index + 1])
            if offset + left >= 0 and offset + right <= width:
                if first is None:
                    first = index
                    first_position = left
                last = index + 1
        if first is None:
            return "", 0.0
        return text[first:last], offset + first_position

    def draw_value_text(self, source, obj, kind, key):
        x, y, width, height = self._get_canpar_text_bounds(source, obj)
        fixed_width, align = self._get_canpar_text_layout(obj)
        tag = "{}_{}".format(kind, key)
        tags = (kind, tag)
        text = self._prepare_canpar_preview_text(source, obj)
        font_spec = self.preview_font(obj.get("fontSize", 18))
        color = parse_color(obj.get("color"))

        if fixed_width is None:
            self.canvas.create_text(
                x, y, text=text, anchor=tk.NW,
                fill=color, font=font_spec, tags=tags
            )
        else:
            font = tkfont.Font(root=self, font=font_spec)
            line_height = font.metrics("linespace")
            for line_index, line in enumerate(text.split("\n")):
                visible, offset = self._clip_preview_text_line(
                    line, font, fixed_width, align
                )
                if not visible:
                    continue
                item = self.canvas.create_text(
                    x + offset, y + line_index * line_height,
                    text=visible, anchor=tk.NW,
                    fill=color, font=font_spec, tags=tags
                )
                bbox = self.canvas.bbox(item)
                if bbox:
                    self.canvas.move(item, x + offset - bbox[0], 0)

        if self.is_selected(kind, key):
            bbox = (
                (x, y, x + width, y + height)
                if fixed_width is not None
                else self.canvas.bbox(tag)
            )
            if bbox is None:
                bbox = (x, y, x + width, y + height)
            self.canvas.create_rectangle(
                bbox[0] - 2, bbox[1] - 2,
                bbox[2] + 2, bbox[3] + 2,
                outline="#FFFF00", dash=(4, 2), tags=("selection",)
            )

    def center_selected(self):
        obj = self.get_selected_object()
        if not isinstance(obj, dict):
            return

        if self.selected_kind == "canpar" and is_scale_canpar(obj):
            scale = get_scale_config(obj)
            width = max(1, safe_int(scale.get("width", 100), 100))
            height = max(1, safe_int(scale.get("height", 100), 100))
            obj["x"] = int((ROUND_AREA_WIDTH - width) / 2)
            obj["y"] = int((ROUND_AREA_HEIGHT - height) / 2)
        elif self.selected_kind == "canpar" or is_text_output(obj):
            source = (
                self.selected_key if self.selected_kind == "canpar"
                else canonical_canpar(obj.get("canpar"))
            )
            _, _, width, height = self._get_canpar_text_bounds(source, obj)
            obj["x"] = round((SCREEN_WIDTH - width) / 2)
            obj["y"] = round((SCREEN_HEIGHT - height) / 2)
        else:
            tag = "{}_{}".format(self.selected_kind, self.selected_key)
            bbox = self.canvas.bbox(tag)
            if bbox:
                obj["x"] = safe_int(obj.get("x")) + round(
                    SCREEN_WIDTH / 2 - (bbox[0] + bbox[2]) / 2
                )
                obj["y"] = safe_int(obj.get("y")) + round(
                    SCREEN_HEIGHT / 2 - (bbox[1] + bbox[3]) / 2
                )
        self.refresh_all()

    def get_preview_value(self, name):
        text = self.preview_text(name).strip()
        match = re.match(
            r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", text
        )
        if not match:
            return None
        value = safe_float(match.group(0), None)
        return value if value is not None and abs(value) <= 1e9 else None

    def is_selected(self, kind, key):
        return (
            self.selected_kind == kind
            and str(self.selected_key) == str(key)
        )

    def draw_preview(self):
        old_images = self.preview_images
        self.preview_images = {}
        self.canvas.delete("all")
        del old_images

        self.canvas.create_rectangle(
            0, 0, SCREEN_WIDTH, SCREEN_HEIGHT,
            fill="#000000", outline=""
        )
        self.canvas.create_oval(
            0, 0, ROUND_AREA_WIDTH, ROUND_AREA_HEIGHT,
            fill="#101010", outline="#FF0000", width=1
        )
        if not self.disable_grid_var.get():
            for x in range(0, SCREEN_WIDTH + 1, 20):
                self.canvas.create_line(
                    x, 0, x, SCREEN_HEIGHT,
                    fill="#FFFF00", tags=("preview_grid",)
                )
            for y in range(0, SCREEN_HEIGHT + 1, 20):
                self.canvas.create_line(
                    0, y, SCREEN_WIDTH, y,
                    fill="#FFFF00", tags=("preview_grid",)
                )
        self.canvas.create_line(
            0, ROUND_AREA_HEIGHT, SCREEN_WIDTH, ROUND_AREA_HEIGHT,
            fill="#555555", dash=(3, 3)
        )

        # Как в прошивке: сначала elements, затем основные canpar.
        # Поэтому одинаковые координаты могут скрывать дубли.
        for index, element in enumerate(self.data.get("elements", [])):
            self.draw_element(index, element)

        canpar = self.data.get("canpar", {})
        for name in CANPAR_NAMES:
            if name in canpar:
                self.draw_canpar(name, canpar[name])
        for name, obj in canpar.items():
            if name not in CANPAR_NAMES:
                self.draw_canpar(name, obj)

        self.canvas.tag_raise("selection")

    def draw_canpar(self, name, obj):
        if not isinstance(obj, dict):
            return
        if not is_scale_canpar(obj):
            self.draw_value_text(name, obj, "canpar", name)
            return

        scale = get_scale_config(obj)
        x = safe_int(obj.get("x", 0))
        y = safe_int(obj.get("y", 0))
        width = max(1, safe_int(scale.get("width", 100), 100))
        height = max(1, safe_int(scale.get("height", 100), 100))

        if is_gradient_canpar(obj):
            self.draw_gradient_round_scale(name, x, y, width, height, scale)
        else:
            mode = scale.get("mode", "round_outer")
            if mode in ("horizontal", "horizontal_top"):
                self._draw_linear_scale(
                    name, x, y, width, height, scale, False
                )
            elif mode in ("vertical", "vertical_left"):
                self._draw_linear_scale(
                    name, x, y, width, height, scale, True
                )
            else:
                self.draw_round_scale(name, x, y, width, height, scale)

        if self.is_selected("canpar", name):
            self.canvas.create_rectangle(
                x, y, x + width, y + height,
                outline="#FFFF00", dash=(4, 2), tags=("selection",)
            )

    def _draw_arc(
        self, cx, cy, radius, start, sweep, color, width,
        tags=(), rounded=False
    ):
        radius = safe_float(radius, 0)
        width = safe_float(width, 0)
        sweep = clamp(safe_float(sweep, 0), 0, 360)
        start = safe_float(start, 0) % 360
        if radius <= 0 or width <= 0 or sweep <= 0:
            return
        color = parse_color(color)
        half = width / 2
        outer = radius + half
        inner = max(0, radius - half)

        remaining = sweep
        current = start
        while remaining > 0.000001:
            part = min(90, remaining)
            steps = max(1, math.ceil(part))
            points = []
            for r, indices in (
                (outer, range(steps + 1)),
                (inner, range(steps, -1, -1))
            ):
                for index in indices:
                    a = math.radians(current + part * index / steps)
                    points.extend((cx + r * math.cos(a), cy + r * math.sin(a)))
            self.canvas.create_polygon(
                *points, fill=color, outline="", smooth=False, tags=tags
            )
            current += part
            remaining -= part

        if rounded and sweep < 360:
            for degrees in (start, start + sweep):
                a = math.radians(degrees)
                px = cx + radius * math.cos(a)
                py = cy + radius * math.sin(a)
                self.canvas.create_oval(
                    px - half, py - half, px + half, py + half,
                    fill=color, outline="", tags=tags
                )

    def scale_range(self, scale, name):
        minimum = safe_float(scale.get("min", 0), 0)
        maximum = safe_float(scale.get("max", 100), 100)
        if maximum <= minimum:
            maximum = minimum + 100
        value = self.get_preview_value(name)
        if value is None:
            value = minimum
        ratio = clamp((value - minimum) / (maximum - minimum), 0, 1)
        return minimum, maximum, ratio

    def draw_gradient_round_scale(self, name, x, y, width, height, scale):
        width = max(6, width)
        height = max(6, height)
        cx = x + width / 2
        cy = y + height / 2
        radius = max(1, (min(width, height) - 2) // 2)
        thickness = clamp(
            safe_int(scale.get("lineWidth", 20), 20), 1, radius
        )
        middle = radius - thickness / 2
        rotation = safe_int(scale.get("rotation", 135), 135) % 360
        sweep = clamp(safe_int(scale.get("angleRange", 270), 270), 1, 360)
        minimum, maximum, ratio = self.scale_range(scale, name)
        filled = sweep * ratio
        tags = ("canpar", "canpar_" + name)
        rounded = bool(scale.get("rounded", True))
        start_color = parse_color(scale.get("startColor"), "#004080")
        end_color = parse_color(scale.get("endColor"), "#40C0FF")

        self._draw_arc(
            cx, cy, middle, rotation, sweep,
            parse_color(scale.get("scaleColor"), "#202020"),
            thickness, tags, rounded
        )
        if filled > 0:
            for index in range(math.ceil(filled)):
                a = float(index)
                b = min(a + 1, filled)
                self._draw_arc(
                    cx, cy, middle, rotation + a, b - a,
                    mix_color(start_color, end_color, (a + b) / 2 / sweep),
                    thickness, tags
                )
            if rounded and filled < 360:
                half = thickness / 2
                for degrees, color in (
                    (rotation, start_color),
                    (rotation + filled, mix_color(start_color, end_color, ratio))
                ):
                    a = math.radians(degrees)
                    px = cx + middle * math.cos(a)
                    py = cy + middle * math.sin(a)
                    self.canvas.create_oval(
                        px - half, py - half, px + half, py + half,
                        fill=color, outline="", tags=tags
                    )

        count = min(2000, max(2, safe_int(scale.get("totalTickCount", 21), 21)))
        every = max(1, safe_int(scale.get("majorTickEvery", 5), 5))
        tick_width = max(0, safe_int(scale.get("tickWidth", 1), 1))
        for index in range(count):
            if sweep == 360 and index == count - 1:
                continue
            r = index / (count - 1)
            a = math.radians(rotation + r * sweep)
            dx, dy = math.cos(a), math.sin(a)
            major = index % every == 0 or index == count - 1

            if scale.get("showTicks", True) and tick_width > 0:
                length = clamp(
                    safe_int(scale.get(
                        "majorTickLength" if major else "minorTickLength",
                        10 if major else 5
                    )), 0, thickness
                )
                if length > 0:
                    self.canvas.create_line(
                        cx + (middle - length / 2) * dx,
                        cy + (middle - length / 2) * dy,
                        cx + (middle + length / 2) * dx,
                        cy + (middle + length / 2) * dy,
                        fill=parse_color(scale.get("tickColor")),
                        width=tick_width, tags=tags
                    )
            if scale.get("showLabels", True) and major:
                self.canvas.create_text(
                    cx + middle * dx, cy + middle * dy,
                    text=format_scale_label(minimum + r * (maximum - minimum)),
                    anchor=tk.CENTER,
                    fill=parse_color(scale.get("labelColor")),
                    font=self.preview_font(scale.get("fontSize", 18)),
                    tags=tags
                )

    def draw_round_scale(self, name, x, y, width, height, scale):
        cx = x + width / 2
        cy = y + height / 2
        radius = max(1, min(width, height) / 2 - 5)
        rotation = safe_float(scale.get("rotation", 135), 135) % 360
        sweep = clamp(safe_float(scale.get("angleRange", 270), 270), 0, 360)
        outer = str(scale.get("mode", "round_outer")).lower() == "round_outer"
        tags = ("canpar", "canpar_" + name)

        self._draw_arc(
            cx, cy, radius, rotation, sweep,
            parse_color(scale.get("scaleColor"), "#404040"),
            max(1, safe_int(scale.get("lineWidth", 2), 2)), tags
        )
        count = min(2000, max(2, safe_int(scale.get("totalTickCount", 21), 21)))
        every = max(1, safe_int(scale.get("majorTickEvery", 5), 5))
        tick_width = max(0, safe_int(scale.get("tickWidth", 2), 2))
        minimum, maximum, ratio = self.scale_range(scale, name)

        for index in range(count):
            if sweep == 360 and index == count - 1:
                continue
            r = index / (count - 1)
            a = math.radians(rotation + r * sweep)
            dx, dy = math.cos(a), math.sin(a)
            major = index % every == 0 or index == count - 1
            length = max(0, safe_int(scale.get(
                "majorTickLength" if major else "minorTickLength",
                10 if major else 5
            )))
            if outer:
                r1, r2, label_r = radius, radius + length, radius + length + 12
            else:
                r1, r2, label_r = radius - length, radius, radius - length - 12

            if scale.get("showTicks", True) and tick_width > 0 and length > 0:
                self.canvas.create_line(
                    cx + r1 * dx, cy + r1 * dy,
                    cx + r2 * dx, cy + r2 * dy,
                    fill=parse_color(scale.get("tickColor")),
                    width=tick_width, tags=tags
                )
            if scale.get("showLabels", True) and major:
                self.canvas.create_text(
                    cx + label_r * dx, cy + label_r * dy,
                    text=format_scale_label(minimum + r * (maximum - minimum)),
                    fill=parse_color(scale.get("labelColor")),
                    font=self.preview_font(scale.get("fontSize", 18)),
                    tags=tags
                )

        a = math.radians(rotation + ratio * sweep)
        length = max(0, safe_float(scale.get("needleLength", radius * 0.65)))
        ex, ey = cx + length * math.cos(a), cy + length * math.sin(a)
        color = parse_color(scale.get("needleColor"), "#FF2020")
        width_n = max(1, safe_int(scale.get("needleWidth", 3), 3))
        self.canvas.create_line(
            cx, cy, ex, ey, fill=color, width=width_n,
            capstyle=tk.ROUND if scale.get("rounded", True) else tk.BUTT,
            tags=tags
        )
        if scale.get("needle", "line") in ("arrow", "triangle"):
            self.draw_arrow_head(cx, cy, ex, ey, color, width_n, tags)
            half = max(5, width_n + 4) / 2
            self.canvas.create_oval(
                cx - half, cy - half, cx + half, cy + half,
                fill="#FFFFFF", outline="", tags=tags
            )

    def _draw_linear_scale(self, name, x, y, width, height, scale, vertical):
        tags = ("canpar", "canpar_" + name)
        cx, cy = x + width / 2, y + height / 2
        line_y = y + clamp(height / 2 + 12, 0, max(0, height - 1))
        main = (
            (cx, y, cx, y + height)
            if vertical else (x, cy, x + width, cy)
        )
        self.canvas.create_line(
            *main, fill=parse_color(scale.get("scaleColor"), "#404040"),
            width=max(1, safe_int(scale.get("lineWidth", 2), 2)), tags=tags
        )
        minimum, maximum, ratio = self.scale_range(scale, name)
        count = min(2000, max(2, safe_int(scale.get("totalTickCount", 11), 11)))
        every = max(1, safe_int(scale.get("majorTickEvery", 2), 2))
        tick_width = max(1, safe_int(scale.get("tickWidth", 2), 2))

        for index in range(count):
            r = index / (count - 1)
            major = index % every == 0 or index == count - 1
            length = max(0, safe_int(scale.get(
                "majorTickLength" if major else "minorTickLength",
                10 if major else 5
            )))
            if vertical:
                px, py = cx, y + height - r * height
                tick = (px, py, px - length, py)
                lx, ly = px - length - max(4, tick_width + 4), py
                anchor = tk.E
            else:
                px, py = x + r * width, cy
                tick = (px, py, px, py - length)
                lx, ly = px, py - length - 8
                anchor = tk.S
            if scale.get("showTicks", True):
                self.canvas.create_line(
                    *tick, fill=parse_color(scale.get("tickColor")),
                    width=tick_width, tags=tags
                )
            if scale.get("showLabels", True) and major:
                self.canvas.create_text(
                    lx, ly, anchor=anchor,
                    text=format_scale_label(minimum + r * (maximum - minimum)),
                    fill=parse_color(scale.get("labelColor")),
                    font=self.preview_font(scale.get("fontSize", 18)),
                    tags=tags
                )

        if vertical:
            sx, sy, ex, ey = cx, y + height, cx, y + height - ratio * height
        else:
            sx, sy, ex, ey = x, line_y, x + ratio * width, line_y
        color = parse_color(scale.get("needleColor"), "#FF2020")
        width_n = max(1, safe_int(scale.get("needleWidth", 3), 3))
        self.canvas.create_line(
            sx, sy, ex, ey, fill=color, width=width_n,
            capstyle=tk.ROUND if scale.get("rounded", True) else tk.BUTT,
            tags=tags
        )
        if scale.get("needle", "line") in ("arrow", "triangle"):
            self.draw_arrow_head(sx, sy, ex, ey, color, width_n, tags)

    def draw_arrow_head(
        self, start_x, start_y, end_x, end_y, color, width, tags=()
    ):
        dx, dy = end_x - start_x, end_y - start_y
        length = math.hypot(dx, dy)
        if length < 0.01:
            return
        dx, dy = dx / length, dy / length
        head_length = min(length, max(6, width + 5))
        head_width = min(max(3, width + 2), head_length * 0.7)
        px, py = -dy, dx
        self.canvas.create_polygon(
            end_x, end_y,
            end_x - dx * head_length + px * head_width,
            end_y - dy * head_length + py * head_width,
            end_x - dx * head_length - px * head_width,
            end_y - dy * head_length - py * head_width,
            fill=color, outline=color, tags=tags
        )

    def draw_element(self, index, element):
        if not isinstance(element, dict):
            return
        if is_text_output(element):
            self.draw_value_text(
                canonical_canpar(element.get("canpar")),
                element, "element", index
            )
            return

        action = is_action_element(element)
        element_id = safe_int(element.get("id", 100), 100)
        kind = str(element.get("type", "")).lower()
        x, y = safe_int(element.get("x")), safe_int(element.get("y"))
        tags = ("element", "element_{}".format(index))
        text_object = not action and (
            element_id in SUPPORTED_TEXT_IDS
            or kind in ("text", "static_text", "dynamic_text")
        )

        if text_object:
            text = (
                "Пн 12.10" if element_id == 101
                else "12:34" if element_id == 102
                else str(element.get("text", "") or "TEXT")
            )
            self.canvas.create_text(
                x, y, text=text, anchor=tk.NW,
                fill=parse_color(element.get("color")),
                font=self.preview_font(element.get("fontSize", 18)),
                tags=tags
            )
        else:
            source = element.get("image", "")
            group = element.get("group", [])
            if not source and isinstance(group, list) and group:
                source = group[0]
            path = self.resolve_asset(source)
            error_text = "BIN не выбран" if not source else "Файл не найден"
            drawn = False
            if path:
                try:
                    photo = self.get_photo_image(path)
                    self.preview_images[index] = photo
                    self.canvas.create_image(
                        x, y, image=photo, anchor=tk.NW, tags=tags
                    )
                    drawn = True
                except Exception as error:
                    error_text = str(error)
            if not drawn:
                title = (
                    canonical_action(element.get("action")) or "ACTION"
                ) if action else "BIN"
                self.canvas.create_rectangle(
                    x, y, x + 90, y + 48,
                    fill="#303030", outline="#FF4444",
                    dash=(3, 2), tags=tags
                )
                self.canvas.create_text(
                    x + 4, y + 4,
                    text="{}\n{}".format(title, error_text),
                    fill="#FF7777", anchor=tk.NW, width=82,
                    font=("Arial", -9), tags=tags
                )

        if self.is_selected("element", index):
            bbox = self.canvas.bbox(tags[1])
            if bbox:
                self.canvas.create_rectangle(
                    *bbox, outline="#FFFF00",
                    dash=(4, 2), tags=("selection",)
                )

    def find_object_at(self, px, py):
        items = self.canvas.find_overlapping(px - 2, py - 2, px + 2, py + 2)
        for item in reversed(items):
            tags = self.canvas.gettags(item)
            if "selection" in tags:
                continue
            for tag in tags:
                if tag.startswith("element_"):
                    return "element", tag[len("element_"):]
                if tag.startswith("canpar_"):
                    return "canpar", tag[len("canpar_"):]

        # Пустые области основных canpar находятся над elements.
        for name, obj in reversed(list(self.data.get("canpar", {}).items())):
            if not isinstance(obj, dict):
                continue
            if is_scale_canpar(obj):
                if is_gradient_canpar(obj):
                    continue
                scale = get_scale_config(obj)
                x, y = safe_int(obj.get("x")), safe_int(obj.get("y"))
                width = max(1, safe_int(scale.get("width", 100), 100))
                height = max(1, safe_int(scale.get("height", 100), 100))
            else:
                width, _ = self._get_canpar_text_layout(obj)
                if width is None:
                    continue
                x, y, width, height = self._get_canpar_text_bounds(name, obj)
            if x <= px < x + width and y <= py < y + height:
                return "canpar", name

        for index in range(len(self.data.get("elements", [])) - 1, -1, -1):
            obj = self.data["elements"][index]
            if not is_text_output(obj):
                continue
            x, y, width, height = self._get_canpar_text_bounds(
                canonical_canpar(obj.get("canpar")), obj
            )
            if x <= px < x + width and y <= py < y + height:
                return "element", str(index)
        return None

    def canvas_mouse_down(self, event):
        self.canvas.focus_set()
        selected = self.find_object_at(event.x, event.y)
        if selected is None:
            self.drag_state = None
            return
        self.select_object(*selected)
        obj = self.get_selected_object()
        if isinstance(obj, dict):
            self.drag_state = {
                "mouse_x": event.x, "mouse_y": event.y,
                "object_x": safe_int(obj.get("x")),
                "object_y": safe_int(obj.get("y"))
            }

    def canvas_mouse_move(self, event):
        obj = self.get_selected_object()
        if self.drag_state is None or not isinstance(obj, dict):
            return
        obj["x"] = (
            self.drag_state["object_x"]
            + event.x - self.drag_state["mouse_x"]
        )
        obj["y"] = (
            self.drag_state["object_y"]
            + event.y - self.drag_state["mouse_y"]
        )
        self.x_var.set(str(obj["x"]))
        self.y_var.set(str(obj["y"]))
        self.draw_preview()

    def canvas_mouse_up(self, event):
        self.drag_state = None

    def canvas_double_click(self, event):
        selected = self.find_object_at(event.x, event.y)
        if not selected or selected[0] != "element":
            return
        index = safe_int(selected[1], -1)
        elements = self.data.get("elements", [])
        if not 0 <= index < len(elements):
            return
        element = elements[index]
        if not isinstance(element, dict) or is_text_output(element):
            return
        source = element.get("image", "")
        group = element.get("group", [])
        if not source and isinstance(group, list) and group:
            source = group[0]
        path = self.resolve_asset(source)
        if path:
            self.open_bin_file(path)

    def move_selected_with_keyboard(self, event):
        focused = self.focus_get()
        if focused is not None and focused.winfo_class() in (
            "Entry", "TEntry", "Text", "Spinbox", "TSpinbox", "TCombobox"
        ):
            return None
        if self.drag_state is not None:
            return None
        obj = self.get_selected_object()
        if not isinstance(obj, dict):
            return None
        movement = {
            "Up": (0, -1), "Down": (0, 1),
            "Left": (-1, 0), "Right": (1, 0)
        }.get(event.keysym)
        if movement is None:
            return None
        obj["x"] = safe_int(obj.get("x")) + movement[0]
        obj["y"] = safe_int(obj.get("y")) + movement[1]
        self.x_var.set(str(obj["x"]))
        self.y_var.set(str(obj["y"]))
        self.draw_preview()
        return "break"

    def get_bin_image(self, path):
        absolute = os.path.abspath(path)
        if not os.path.isfile(absolute):
            raise FileNotFoundError("BIN не найден:\n" + absolute)
        stat = os.stat(absolute)
        signature = (stat.st_mtime_ns, stat.st_size)
        cached = self.bin_cache.get(absolute)
        if cached is not None and getattr(cached, "_signature", None) == signature:
            return cached
        image = LvglBinImage(absolute)
        image._signature = signature
        self.bin_cache[absolute] = image
        return image

    def get_photo_image(self, path):
        image = self.get_bin_image(path)
        photo = tk.PhotoImage(
            master=self, width=image.width, height=image.height
        )
        for y, row in enumerate(image.pixels):
            for x, pixel in enumerate(row):
                red, green, blue = pixel[:3]
                alpha = pixel[3] if len(pixel) == 4 else 255
                if alpha == 0:
                    continue
                if alpha < 255:
                    red = red * alpha // 255
                    green = green * alpha // 255
                    blue = blue * alpha // 255
                photo.put(
                    "#{:02X}{:02X}{:02X}".format(red, green, blue),
                    to=(x, y)
                )
        return photo

    def resolve_asset(self, value):
        if not isinstance(value, str) or not value.strip():
            return None
        text = value.strip()
        device_path = text[:2].upper() == "S:"
        if device_path:
            text = text[2:]
        text = text.replace("\\", os.sep).replace("/", os.sep)
        relative = text.lstrip("\\/")
        basename = os.path.basename(relative)

        directories = []
        if self.filename:
            directories.append(os.path.dirname(os.path.abspath(self.filename)))
        if self.asset_directory:
            directories.append(os.path.abspath(self.asset_directory))
        candidates = []
        if not device_path and os.path.isabs(text):
            candidates.append(text)
        candidates.extend(os.path.join(d, relative) for d in directories)
        candidates.extend(os.path.join(d, basename) for d in directories)
        candidates.append(relative)

        seen = set()
        for candidate in candidates:
            absolute = os.path.abspath(os.path.normpath(candidate))
            key = os.path.normcase(absolute)
            if key not in seen and os.path.isfile(absolute):
                return absolute
            seen.add(key)
        return None

    def _asset_reference(self, filename):
        filename = os.path.abspath(filename)
        directory = self.asset_directory or (
            os.path.dirname(os.path.abspath(self.filename))
            if self.filename else os.path.dirname(filename)
        )
        try:
            relative = os.path.relpath(filename, directory)
        except ValueError as error:
            raise ValueError(
                "BIN находится на другом диске. "
                "Поместите его в каталог ресурсов."
            ) from error
        if (
            relative == os.pardir
            or relative.startswith(os.pardir + os.sep)
            or os.path.isabs(relative)
        ):
            raise ValueError(
                "BIN находится вне каталога ресурсов:\n{}\n\n"
                "Скопируйте его в этот каталог или подпапку.".format(directory)
            )
        self.asset_directory = directory
        relative = relative.replace("\\", "/")
        return "S:/" + relative, "/" + relative

    def select_bin_for_element(self):
        element = self.get_selected_object()
        if (
            self.selected_kind != "element"
            or not isinstance(element, dict)
            or is_text_output(element)
        ):
            return
        filename = filedialog.askopenfilename(
            parent=self, title="Выбрать LVGL BIN",
            filetypes=[("BIN files", "*.bin"), ("All files", "*.*")]
        )
        if not filename:
            return
        try:
            image = self.get_bin_image(filename)
            reference, asset = self._asset_reference(filename)
            element["image"] = reference
            self.element_image_var.set(reference)
            assets = self.data.setdefault("assets", [])
            if asset not in assets:
                assets.append(asset)
            self.refresh_object_list()
            self.draw_preview()
            messagebox.showinfo(
                "BIN", "Загружено: {}×{}, format=0x{:02X}".format(
                    image.width, image.height, image.color_format
                ), parent=self
            )
        except Exception as error:
            messagebox.showerror("Ошибка BIN", str(error), parent=self)

    def open_selected_bin(self):
        element = self.get_selected_object()
        if not isinstance(element, dict) or is_text_output(element):
            return
        source = element.get("image", "")
        group = element.get("group", [])
        if not source and isinstance(group, list) and group:
            source = group[0]
        path = self.resolve_asset(source)
        if path:
            self.open_bin_file(path)
        else:
            messagebox.showwarning(
                "BIN", "Файл изображения не найден.", parent=self
            )

    def add_bin_asset(self):
        filename = filedialog.askopenfilename(
            parent=self, title="Добавить BIN",
            filetypes=[("BIN files", "*.bin"), ("All files", "*.*")]
        )
        if not filename:
            return
        try:
            image = self.get_bin_image(filename)
            reference, asset = self._asset_reference(filename)
            assets = self.data.setdefault("assets", [])
            if asset not in assets:
                assets.append(asset)
            messagebox.showinfo(
                "BIN", "Добавлен {}\nРазмер: {}×{}".format(
                    reference, image.width, image.height
                ), parent=self
            )
        except Exception as error:
            messagebox.showerror("Ошибка BIN", str(error), parent=self)

    def open_bin(self):
        filename = filedialog.askopenfilename(
            parent=self, title="Открыть LVGL BIN",
            filetypes=[("BIN files", "*.bin"), ("All files", "*.*")]
        )
        if filename:
            self.open_bin_file(filename)

    def open_bin_file(self, filename):
        try:
            image = self.get_bin_image(filename)
            window = tk.Toplevel(self)
            window.title("BIN: {} — {}×{}".format(
                os.path.basename(filename), image.width, image.height
            ))
            window.geometry("760x620")
            ttk.Label(
                window,
                text=(
                    "Файл: {}\nРазмер: {}×{}\nStride: {}\n"
                    "Color format: 0x{:02X}\nРазмер файла: {} байт"
                ).format(
                    filename, image.width, image.height,
                    image.stride, image.color_format, len(image.raw)
                ),
                wraplength=730
            ).pack(anchor=tk.W, padx=8, pady=8)
            photo = self.get_photo_image(filename)
            label = ttk.Label(window, image=photo)
            label.image = photo
            label.pack(expand=True, pady=8)
            text = tk.Text(
                window, height=8, wrap=tk.NONE, font=("Consolas", 9)
            )
            text.pack(fill=tk.BOTH, padx=8, pady=8)
            text.insert(
                "1.0", "Header: " + " ".join(
                    "{:02X}".format(b)
                    for b in image.raw[:LV_IMAGE_HEADER_SIZE]
                ) + "\n\n"
            )
            for offset in range(0, min(len(image.raw), 256), 16):
                text.insert(tk.END, "{:04X}: {}\n".format(
                    offset, " ".join(
                        "{:02X}".format(b)
                        for b in image.raw[offset:offset + 16]
                    )
                ))
            text.configure(state=tk.DISABLED)
        except Exception as error:
            messagebox.showerror("Ошибка BIN", str(error), parent=self)

    def new_document(self):
        if not messagebox.askyesno(
            "Новый документ", "Создать новый циферблат?", parent=self
        ):
            return
        self.data = make_default_json()
        self.filename = None
        self.asset_directory = None
        self.selected_kind = None
        self.selected_key = None
        self.drag_state = None
        self.bin_cache.clear()
        self.refresh_all()

    def open_json(self):
        filename = filedialog.askopenfilename(
            parent=self, title="Открыть JSON",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not filename:
            return
        try:
            with open(filename, "r", encoding="utf-8-sig") as file:
                loaded = json.load(file)
            if not isinstance(loaded, dict):
                raise ValueError("Корневой JSON должен быть объектом.")
            for field, expected, default in (
                ("canpar", dict, {}),
                ("elements", list, []),
                ("assets", list, [])
            ):
                if field not in loaded:
                    loaded[field] = deep_copy(default)
                elif not isinstance(loaded[field], expected):
                    raise ValueError("Некорректный тип поля {}.".format(field))
            loaded.setdefault("name", "Custom face")
            normalize_document_font_sizes(loaded)

            self.data = loaded
            self.filename = os.path.abspath(filename)
            self.asset_directory = os.path.dirname(self.filename)
            self.selected_kind = None
            self.selected_key = None
            self.drag_state = None
            self.bin_cache.clear()
            self.refresh_all()

            if self.count_text_outputs() > MAX_TEXT_OUTPUTS:
                messagebox.showwarning(
                    "Текстовые выводы",
                    "В JSON больше 3 текстовых выводов.\n"
                    "Удалите лишние перед сохранением.",
                    parent=self
                )
        except json.JSONDecodeError as error:
            messagebox.showerror(
                "Ошибка JSON", "Строка {}, столбец {}:\n{}".format(
                    error.lineno, error.colno, error.msg
                ), parent=self
            )
        except Exception as error:
            messagebox.showerror("Ошибка JSON", str(error), parent=self)

    def save_json(self):
        if not self.filename:
            return self.save_json_as()
        return self.write_json(self.filename)

    def save_json_as(self):
        filename = filedialog.asksaveasfilename(
            parent=self, title="Сохранить JSON",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not filename:
            return False
        filename = os.path.abspath(filename)
        if not self.write_json(filename):
            return False
        self.filename = filename
        self.asset_directory = os.path.dirname(filename)
        return True

    def text_layout_errors(self, obj, label):
        errors = []
        if "width" in obj:
            width = obj["width"]
            if type(width) is not int or not 1 <= width <= 32767:
                errors.append(
                    "{}.width: требуется целое число 1…32767.".format(label)
                )
        if "align" in obj:
            align = obj["align"]
            if type(align) is not int or align not in (0, 1, 2):
                errors.append(
                    "{}.align: требуется целое число 0, 1 или 2.".format(label)
                )
        return errors

    def text_output_errors(self):
        errors = []
        outputs = [
            (index, obj)
            for index, obj in enumerate(self.data.get("elements", []))
            if is_text_output(obj)
        ]
        if len(outputs) > MAX_TEXT_OUTPUTS:
            errors.append("Разрешено максимум 3 текстовых вывода.")
        for index, obj in outputs:
            label = "elements[{}] (text_output)".format(index)
            if not canonical_canpar(obj.get("canpar")):
                errors.append(
                    "{}: источник должен быть canpar1, canpar2 или canpar3."
                    .format(label)
                )
            errors.extend(self.text_layout_errors(obj, label))
            bad_fields = sorted(
                field for field in TEXT_OUTPUT_FORBIDDEN_FIELDS
                if field in obj
            )
            if bad_fields:
                errors.append(
                    "{}: недопустимые свойства: {}. "
                    "Примените свойства объекта для очистки."
                    .format(label, ", ".join(bad_fields))
                )
            if "showUnit" in obj and type(obj["showUnit"]) is not bool:
                errors.append(
                    "{}.showUnit: требуется true или false.".format(label)
                )
            if "color" in obj and parse_color(obj["color"], None) is None:
                errors.append("{}: некорректный color.".format(label))
        return errors

    def write_json(self, filename):
        try:
            output_errors = self.text_output_errors()
            if output_errors:
                raise ValueError("\n".join(output_errors))
            normalize_document_font_sizes(self.data)
            self.apply_name()
            serialized = json.dumps(
                self.data, ensure_ascii=False, indent=2, allow_nan=False
            )
            with open(filename, "w", encoding="utf-8") as file:
                file.write(serialized + "\n")
            messagebox.showinfo("Сохранение", "JSON сохранён.", parent=self)
            return True
        except Exception as error:
            messagebox.showerror("Ошибка сохранения", str(error), parent=self)
            return False

    def apply_name(self):
        self.data["name"] = self.name_var.get().strip() or "Custom face"
        self.name_var.set(self.data["name"])

    def validate_document(self):
        errors = []
        warnings = []
        canpar = self.data.get("canpar", {})
        if not isinstance(canpar, dict):
            errors.append("Поле canpar должно быть объектом.")
            canpar = {}

        for name, obj in canpar.items():
            if name not in CANPAR_NAMES:
                warnings.append(
                    "{}: прошивка поддерживает только canpar1..3.".format(name)
                )
            if not isinstance(obj, dict):
                errors.append("{} должен быть объектом.".format(name))
                continue
            kind = str(obj.get("type", "text")).lower()
            if kind not in SUPPORTED_CANPAR_TYPES:
                warnings.append("{}: неизвестный type={!r}.".format(name, kind))

            if not is_scale_canpar(obj):
                errors.extend(self.text_layout_errors(obj, name))
                width, align = self._get_canpar_text_layout(obj)
                if width is None and align in (1, 2):
                    warnings.append(
                        "{}: align без width не создаёт области "
                        "для заметного выравнивания.".format(name)
                    )
                continue

            if "scale" in obj and not isinstance(obj["scale"], dict):
                errors.append("{}.scale должен быть объектом.".format(name))
                continue

            scale = get_scale_config(obj)
            gradient = is_gradient_canpar(obj)
            mode = scale.get("mode", "round_outer")
            if not gradient and mode not in SUPPORTED_SCALE_MODES:
                errors.append("{}: неизвестный mode={!r}.".format(name, mode))
            if "align" in obj or "align" in scale:
                warnings.append("{}: шкала игнорирует align.".format(name))
            variant = str(scale.get("variant", "")).lower()
            if variant and variant != "gradient_round":
                warnings.append(
                    "{}: неизвестный variant={!r}.".format(name, variant)
                )

            minimum = safe_float(scale.get("min", 0), None)
            maximum = safe_float(scale.get("max", 100), None)
            if minimum is None or maximum is None or maximum <= minimum:
                errors.append("{}: требуется min < max.".format(name))

            width = safe_int(scale.get("width", 120), 0)
            height = safe_int(scale.get("height", 120), 0)
            if width <= 0 or height <= 0:
                errors.append("{}: width и height должны быть > 0.".format(name))
            count = safe_int(scale.get("totalTickCount", 21))
            if count < 2:
                errors.append("{}: totalTickCount меньше 2.".format(name))
            elif count > 2000:
                warnings.append(
                    "{}: предпросмотр ограничен 2000 делениями.".format(name)
                )
            if safe_int(scale.get("majorTickEvery", 5)) < 1:
                errors.append("{}: majorTickEvery должен быть >= 1.".format(name))

            if gradient:
                angle = safe_int(scale.get("angleRange", 270), 0)
                thickness = safe_int(scale.get("lineWidth", 15), 0)
                if not 1 <= angle <= 360:
                    errors.append("{}: angleRange должен быть 1..360.".format(name))
                if not 1 <= thickness <= (min(width, height) - 2) // 2:
                    errors.append("{}: недопустимая толщина lineWidth.".format(name))
                if angle == 360 and scale.get("showLabels", True):
                    warnings.append(
                        "{}: конечная подпись полного круга не рисуется."
                        .format(name)
                    )
                for field in ("startColor", "endColor"):
                    if field in scale and parse_color(scale[field], None) is None:
                        errors.append("{}: некорректный {}.".format(name, field))
                if (
                    scale.get("showLabels", True)
                    and safe_int(scale.get("fontSize", 18), 18) > thickness
                ):
                    warnings.append(
                        "{}: высота шрифта больше толщины дуги.".format(name)
                    )

        elements = self.data.get("elements", [])
        if not isinstance(elements, list):
            errors.append("Поле elements должно быть массивом.")
            elements = []
        else:
            errors.extend(self.text_output_errors())

        actions = set()
        for index, element in enumerate(elements):
            label = "elements[{}]".format(index)
            if not isinstance(element, dict):
                errors.append("{} должен быть объектом.".format(label))
                continue
            if is_text_output(element):
                width, align = self._get_canpar_text_layout(element)
                if width is None and align in (1, 2):
                    warnings.append(
                        "{}: align без width почти незаметен.".format(label)
                    )
                # Отсутствие основного canpar не является ошибкой.
                continue

            if is_action_element(element):
                action = canonical_action(element.get("action"))
                if action not in SUPPORTED_ACTIONS:
                    errors.append(
                        "{}: неизвестный action={!r}.".format(label, action)
                    )
                elif action in actions:
                    errors.append(
                        "{}: повторный индикатор {}.".format(label, action)
                    )
                actions.add(action)
                source = element.get("image", "")
                if not isinstance(source, str) or not source.strip():
                    errors.append("{}: для action требуется image.".format(label))
                else:
                    path = self.resolve_asset(source)
                    if not path:
                        warnings.append("{}: BIN не найден на компьютере.".format(label))
                    else:
                        try:
                            self.get_bin_image(path)
                        except Exception as error:
                            errors.append("{}: ошибка BIN: {}".format(label, error))
                continue

            element_id = safe_int(element.get("id", 100), 100)
            if element_id in SUPPORTED_IMAGE_IDS:
                if not element.get("image") and not element.get("group"):
                    warnings.append("{}: не указан image.".format(label))
            elif element_id not in SUPPORTED_TEXT_IDS:
                warnings.append(
                    "{}: неизвестный id={}.".format(label, element_id)
                )

        if errors:
            text = "\n".join(errors)
            if warnings:
                text += "\n\nПредупреждения:\n" + "\n".join(warnings)
            messagebox.showerror("Проверка JSON", text, parent=self)
        elif warnings:
            messagebox.showwarning(
                "Проверка JSON",
                "Ошибок нет.\n\nПредупреждения:\n" + "\n".join(warnings),
                parent=self
            )
        else:
            messagebox.showinfo(
                "Проверка JSON",
                "JSON соответствует поддерживаемой структуре.",
                parent=self
            )

    def check_round_area(self):
        self.draw_preview()
        warnings = []

        def outside(px, py):
            return math.hypot(
                px - ROUND_CENTER_X, py - ROUND_CENTER_Y
            ) > ROUND_RADIUS + 0.5

        def item_outside(item):
            kind = self.canvas.type(item)
            coords = self.canvas.coords(item)
            if kind in ("arc", "oval") and len(coords) >= 4:
                x1, y1, x2, y2 = coords[:4]
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                rx, ry = abs(x2 - x1) / 2, abs(y2 - y1) / 2
                if kind == "arc":
                    start = safe_float(self.canvas.itemcget(item, "start"))
                    extent = safe_float(self.canvas.itemcget(item, "extent"))
                else:
                    start, extent = 0, 360
                half = safe_float(self.canvas.itemcget(item, "width")) / 2
                samples = max(2, int(abs(extent)) + 1)
                for index in range(samples + 1):
                    a = math.radians(start + extent * index / samples)
                    if outside(
                        cx + (rx + half) * math.cos(a),
                        cy - (ry + half) * math.sin(a)
                    ):
                        return True
                return False
            if kind == "line":
                half = safe_float(self.canvas.itemcget(item, "width")) / 2
                for index in range(0, len(coords), 2):
                    px, py = coords[index:index + 2]
                    if math.hypot(
                        px - ROUND_CENTER_X, py - ROUND_CENTER_Y
                    ) + half > ROUND_RADIUS + 0.5:
                        return True
                return False
            bbox = self.canvas.bbox(item)
            if not bbox:
                return False
            x1, y1, x2, y2 = bbox
            return any(
                outside(px, py)
                for px, py in (
                    (x1, y1), (x2, y1), (x1, y2), (x2, y2)
                )
            )

        objects = [
            (name, "canpar_" + name)
            for name in self.data.get("canpar", {})
        ]
        objects.extend(
            ("elements[{}]".format(i), "element_{}".format(i))
            for i in range(len(self.data.get("elements", [])))
        )
        for label, tag in objects:
            if any(
                item_outside(item)
                for item in self.canvas.find_withtag(tag)
            ):
                warnings.append(label + " выходит за круглую область.")

        if warnings:
            messagebox.showwarning(
                "Круглая область", "\n".join(warnings), parent=self
            )
        else:
            messagebox.showinfo(
                "Круглая область",
                "Нарисованные объекты находятся внутри круглой области.\n"
                "Проверка относится к текущим тестовым значениям.",
                parent=self
            )

    def show_json(self):
        window = tk.Toplevel(self)
        window.title("JSON — Editor " + EDITOR_VERSION)
        window.geometry("780x650")
        window.rowconfigure(0, weight=1)
        window.columnconfigure(0, weight=1)
        text = tk.Text(window, wrap=tk.NONE, font=("Consolas", 10))
        text.grid(row=0, column=0, sticky="nsew")
        sy = ttk.Scrollbar(
            window, orient=tk.VERTICAL, command=text.yview
        )
        sy.grid(row=0, column=1, sticky="ns")
        sx = ttk.Scrollbar(
            window, orient=tk.HORIZONTAL, command=text.xview
        )
        sx.grid(row=1, column=0, sticky="ew")
        text.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        text.insert(
            "1.0", json.dumps(self.data, ensure_ascii=False, indent=2)
        )
        text.configure(state=tk.DISABLED)

    def group_to_text(self, group):
        if not isinstance(group, list):
            return ""
        return "; ".join(str(item) for item in group)

    def text_to_group(self, text):
        return [
            item.strip()
            for item in re.split(r"[;\r\n]+", text or "")
            if item.strip()
        ]


if __name__ == "__main__":
    app = DialEditor()
    app.mainloop()