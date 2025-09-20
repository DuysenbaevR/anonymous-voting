#!/bin/bash

# Скрипт автоматической установки системы анонимного голосования
# Использование: chmod +x setup.sh && ./setup.sh

echo "🗳️  Установка системы анонимного голосования"
echo "============================================="

# Проверяем наличие Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 не найден. Установите Python 3.11 или новее."
    exit 1
fi

# Проверяем версию Python
PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
REQUIRED_VERSION="3.11"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" = "$REQUIRED_VERSION" ]; then 
    echo "✅ Python версии $PYTHON_VERSION найден"
else
    echo "❌ Требуется Python 3.11 или новее. Текущая версия: $PYTHON_VERSION"
    exit 1
fi

# Создаем виртуальное окружение
echo "📦 Создание виртуального окружения..."
python3 -m venv venv

# Активируем виртуальное окружение
source venv/bin/activate

# Обновляем pip
echo "🔄 Обновление pip..."
pip install --upgrade pip

# Устанавливаем зависимости
echo "📚 Установка зависимостей..."
pip install -r requirements.txt

# Создаем директорию static
echo "📁 Создание директорий..."
mkdir -p static
mkdir -p logs

# Копируем HTML файлы (если они есть в текущей директории)
if [ -f "index.html" ]; then
    cp index.html static/
    echo "✅ index.html скопирован"
fi

if [ -f "admin.html" ]; then
    cp admin.html static/
    echo "✅ admin.html скопирован"
fi

if [ -f "projector.html" ]; then
    cp projector.html static/
    echo "✅ projector.html скопирован"
fi

# Создаем скрипт запуска
cat > start_server.sh << 'EOF'
#!/bin/bash
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
EOF

chmod +x start_server.sh

# Создаем скрипт остановки
cat > stop_server.sh << 'EOF'
#!/bin/bash
pkill -f "uvicorn main:app"
echo "Сервер остановлен"
EOF

chmod +x stop_server.sh

echo ""
echo "🎉 Установка завершена!"
echo ""
echo "Для запуска системы выполните:"
echo "  ./start_server.sh"
echo ""
echo "Затем откройте в браузере:"
echo "  http://localhost:8000"
echo ""
echo "Для остановки сервера:"
echo "  ./stop_server.sh"
echo ""
echo "📖 Подробную документацию смотрите в README.md"
