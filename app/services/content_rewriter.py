"""
Content Rewriter для zenzefi_backend
Перезаписывает URL в HTML/CSS/JS контенте для корректного проксирования
"""
import re
from typing import Dict, Optional
from loguru import logger


class ContentRewriter:
    """Перезаписывает URL в контенте для проксирования"""

    def __init__(self, upstream_url: str, backend_url: str):
        """
        Args:
            upstream_url: Оригинальный URL (например: https://zenzefi.melxiory.ru)
            backend_url: URL бэкенда (например: https://api.zenzefi.com)
        """
        self.upstream_url = upstream_url.rstrip('/')
        self.backend_url = backend_url.rstrip('/')

        # Компилируем регулярные выражения для производительности
        self._compile_patterns()

        logger.info(f"ContentRewriter: {self.upstream_url} → {self.backend_url}")

    def _compile_patterns(self):
        """Компилирует регулярные выражения для замены URL"""
        upstream_escaped = re.escape(self.upstream_url)

        # Паттерны для разных форматов URL
        self.patterns = [
            # https://zenzefi.melxiory.ru
            (re.compile(rf'https?://{re.escape(self.upstream_url.split("://")[1])}', re.IGNORECASE),
             self.backend_url),

            # "https://zenzefi.melxiory.ru"
            (re.compile(rf'"https?://{re.escape(self.upstream_url.split("://")[1])}"', re.IGNORECASE),
             f'"{self.backend_url}"'),

            # 'https://zenzefi.melxiory.ru'
            (re.compile(rf"'https?://{re.escape(self.upstream_url.split('://')[1])}'", re.IGNORECASE),
             f"'{self.backend_url}'"),

            # //zenzefi.melxiory.ru (protocol-relative)
            (re.compile(rf'//{re.escape(self.upstream_url.split("://")[1])}', re.IGNORECASE),
             f'//{self.backend_url.split("://")[1]}'),

            # WebSocket URLs: wss://zenzefi.melxiory.ru → wss://api.zenzefi.com
            (re.compile(rf'wss://{re.escape(self.upstream_url.split("://")[1])}', re.IGNORECASE),
             f'wss://{self.backend_url.split("://")[1]}'),
        ]

    def rewrite_content(self, content: bytes, content_type: Optional[str] = None) -> bytes:
        """
        Перезаписывает URL в контенте

        Args:
            content: Исходный контент
            content_type: MIME тип контента

        Returns:
            Перезаписанный контент
        """
        # Применяем перезапись только для текстовых форматов
        if not self._is_text_content(content_type):
            return content

        try:
            # Декодируем контент
            text = content.decode('utf-8', errors='ignore')

            # Применяем все паттерны замены
            for pattern, replacement in self.patterns:
                text = pattern.sub(replacement, text)

            # Кодируем обратно
            return text.encode('utf-8')

        except Exception as e:
            logger.error(f"Ошибка перезаписи контента: {e}")
            return content

    def rewrite_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        """
        Перезаписывает URL в заголовках

        Args:
            headers: Исходные заголовки

        Returns:
            Обновленные заголовки
        """
        rewritten_headers = {}

        for key, value in headers.items():
            # Перезаписываем заголовки с URL
            if key.lower() in ['location', 'content-location', 'referer']:
                value = value.replace(self.upstream_url, self.backend_url)

            # Перезаписываем CORS заголовки
            if key.lower() == 'access-control-allow-origin':
                if value == self.upstream_url:
                    value = self.backend_url

            rewritten_headers[key] = value

        return rewritten_headers

    def _is_text_content(self, content_type: Optional[str]) -> bool:
        """Проверяет, является ли контент текстовым"""
        if not content_type:
            return False

        text_types = [
            'text/',
            'application/json',
            'application/javascript',
            'application/xml',
            'application/x-javascript',
            '+xml',
            '+json'
        ]

        content_type_lower = content_type.lower()
        return any(t in content_type_lower for t in text_types)


# Singleton instance
_content_rewriter: Optional[ContentRewriter] = None


def get_content_rewriter(upstream_url: str, backend_url: str) -> ContentRewriter:
    """Получить singleton экземпляр ContentRewriter"""
    global _content_rewriter

    if _content_rewriter is None:
        _content_rewriter = ContentRewriter(upstream_url, backend_url)

    return _content_rewriter
