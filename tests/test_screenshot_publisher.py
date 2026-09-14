"""Exercise preview scheduling without importing device backends or connecting an emulator."""
import ast
from pathlib import Path
import queue
import threading
import time
import unittest


source = Path(__file__).resolve().parents[1] / 'module/device/screenshot.py'
tree = ast.parse(source.read_text(encoding='utf-8'))
publisher_node = next(node for node in tree.body
                      if isinstance(node, ast.ClassDef) and node.name == '_ScreenshotPublisher')


class Encoder:
    COLOR_RGB2BGR = 1
    IMWRITE_JPEG_QUALITY = 2

    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.release.set()

    def cvtColor(self, image, conversion):
        return image

    def imencode(self, extension, image, options):
        self.entered.set()
        self.release.wait(2)
        return True, image


class Frame:
    def __init__(self, value):
        self.value = value

    def tobytes(self):
        return self.value


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.encoder = Encoder()
        namespace = dict(queue=queue, threading=threading, time=time, cv2=self.encoder)
        exec(compile(ast.Module(body=[publisher_node], type_ignores=[]), str(source), 'exec'), namespace)
        self.transport = queue.Queue(maxsize=1)
        self.publisher = namespace['_ScreenshotPublisher'](self.transport, interval=0.1)

    def tearDown(self):
        self.encoder.release.set()
        self.publisher.close()

    def test_final_capture_and_coalescing(self):
        self.publisher.submit(Frame(b'commissions'))
        self.assertEqual(self.transport.get(timeout=1), b'commissions')
        self.publisher.submit(Frame(b'transition'))
        self.publisher.submit(Frame(b'main'))
        self.assertEqual(self.transport.get(timeout=1), b'main')
        with self.assertRaises(queue.Empty):
            self.transport.get(timeout=0.15)

    def test_capture_during_encoding_is_not_lost(self):
        self.encoder.release.clear()
        self.publisher.submit(Frame(b'old'))
        self.assertTrue(self.encoder.entered.wait(1))
        self.publisher.submit(Frame(b'new'))
        self.encoder.release.set()
        self.assertEqual(self.transport.get(timeout=1), b'old')
        self.assertEqual(self.transport.get(timeout=1), b'new')

    def test_close_flushes_and_replaces_full_queue(self):
        self.publisher.interval = 10
        self.publisher.submit(Frame(b'old'))
        self.assertEqual(self.transport.get(timeout=1), b'old')
        self.transport.put_nowait(b'stale')
        self.publisher.submit(Frame(b'final'))
        self.publisher.close()
        self.assertFalse(self.publisher.thread.is_alive())
        self.assertEqual(self.transport.get_nowait(), b'final')

    def test_close_wait_is_bounded(self):
        self.encoder.release.clear()
        self.publisher.submit(Frame(b'final'))
        self.assertTrue(self.encoder.entered.wait(1))
        started = time.monotonic()
        self.publisher.close(timeout=0.02)
        self.assertLess(time.monotonic() - started, 0.5)


if __name__ == '__main__':
    unittest.main()
