import re

def extract_name_from_nick(nick: str):
    # Удаляем стандартные префиксы (например, SAI, SA, D.Head и т. д.)
    nick = re.sub(r'^(SAI|SA|D\.Head|Head|Cur\.|Ass\.Shr\.)\s+', '', nick).strip()
    # Убираем оставшиеся префиксы до первого разделителя
    nick = re.sub(r'^[^|/\\]*[|/\\]\s*', '', nick).strip()
    # Заменяем разделители (|, /, \) на пробелы
    nick = re.sub(r'\s*[|/\\]+\s*', ' ', nick).strip()
    # Убираем "I" в начале строки или как разделитель
    nick = re.sub(r'^I\s+|(?<=\s)I(?=\s)', '', nick).strip()
    # Удаляем ID (цифры в конце)
    nick = re.sub(r'\s+\d+$', '', nick).strip()

    return nick


nick = ['H.Inst.SAI | Oleg Centrao |40360', 'SAI I Estelle Miyazaki I 88022', 'SA | Ilyha Vasnesov | 82219', 'SA | Terrera Mason | 86813', 'SAI | Jac Mason | 2410', 'Ass.Shr. | Robert Centrao | 1005', 'D.Head SAI|Dimitar Centrao|85191', 'Cur. SAI | Mary Centrao | 31431', 'Head SAI | Andy Miyazaki | 28973']


for name in nick:
    print(extract_name_from_nick(name))