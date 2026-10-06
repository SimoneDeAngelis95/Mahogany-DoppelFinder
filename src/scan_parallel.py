"""Bounded media scheduling. Memory estimates are budgets, not guarantees."""
from collections import deque
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from contextlib import contextmanager
from pathlib import Path
import os
import re
import subprocess
import sys
import threading
import time
from PIL import Image

MiB = 1024 * 1024
_local = threading.local()


def media_threads():
    return getattr(_local, 'media_threads', None)


@contextmanager
def decoding_budget():
    previous = media_threads()
    _local.media_threads = 2
    try: yield
    finally: _local.media_threads = previous


def available_memory():
    """Available/reclaimable RAM; unknown platforms use a conservative fallback."""
    try:
        if sys.platform == 'darwin':
            output = subprocess.run(['/usr/bin/vm_stat'], capture_output=True, text=True,
                                    timeout=1, check=True).stdout
            page = int(re.search(r'page size of (\d+) bytes', output).group(1))
            pages = sum(int(re.search(r'^'+re.escape(name)+r':\s+(\d+)', output, re.M).group(1))
                        for name in ('Pages free', 'Pages inactive', 'Pages speculative'))
            return page * pages
        if sys.platform.startswith('linux'):
            output = Path('/proc/meminfo').read_text()
            return int(re.search(r'MemAvailable:\s+(\d+)', output).group(1)) * 1024
    except (OSError, ValueError, AttributeError, subprocess.SubprocessError):
        pass
    return 512 * MiB


def estimate_cost(path):
    suffix = Path(path).suffix.lower()
    if suffix in {'.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm', '.m4v', '.mpeg'}:
        # FFmpeg uses streaming buffers; compressed file size/duration is not RAM usage.
        try:
            from FFmpegAdapter import FFmpegAdapter
            info = FFmpegAdapter().get_video_info(path)
            pixels = (info.get('width') or 3840) * (info.get('height') or 2160)
            return max(768 * MiB, pixels * 128), 'video'
        except Exception:
            return 1024 * MiB, 'video' 
    try:
        with Image.open(path) as image:
            width, height = image.size
            return max(64 * MiB, width * height * 24), 'image'
    except (OSError, ValueError, Image.DecompressionBombError):
        return 128 * MiB, 'other'


class AdaptivePolicy:
    def __init__(self, workers=0, memory=available_memory, cpu=None):
        self.automatic = workers == 0
        self.maximum = min(4, max(1, (cpu or os.cpu_count() or 2) // 2)) if self.automatic else max(1, min(4, workers))
        self.limit = min(2, self.maximum)
        if not self.automatic: self.limit = self.maximum
        self.memory = memory
        self.free = 512 * MiB; self.sampled = float('-inf')
        self.completed = 0; self.durations = deque(maxlen=8)

    def refresh(self):
        now = time.monotonic()
        if now - self.sampled >= 1:
            self.free = self.memory(); self.sampled = now
            if self.automatic and self.free < 768 * MiB:
                self.limit = 1

    def can_start(self, cost, kind, active):
        self.refresh()
        if not active: return True  # A large file must still be able to progress alone.
        if len(active) >= self.limit: return False
        if kind == 'video' and sum(k == 'video' for _, k in active) >= 2: return False
        budget = max(0, self.free - 512 * MiB) * .5
        return sum(c for c, _ in active) + cost <= budget

    def finished(self, elapsed):
        self.completed += 1; self.durations.append(elapsed)
        self.refresh()
        if self.automatic and sum(self.durations) / len(self.durations) > 3:
            self.limit = min(self.limit, 2)
        # Ramp up only after useful work and with ample RAM; slow decodes stay modest.
        if self.automatic and self.completed >= self.limit * 2 and self.free > 2 * 1024 * MiB:
            if sum(self.durations) / len(self.durations) < 2:
                self.limit = min(self.maximum, self.limit + 1)


def parallel_records(candidates, fingerprint, signature, cancel, check_cancel, progress,
                     workers=0, policy=None, activity=None, estimate=None):
    """Decode each physical snapshot once; return deterministic input-order records.

    Only bounded active futures exist. All progress calls run on the scan coordinator.
    Activity callbacks (slot, side, path) run on decoder threads; an empty path
    means idle. Slots identify actual pool threads for the lifetime of this scan.
    Errors are returned per file; cancellation cancels queued work and drains running work.
    """
    estimate = estimate or estimate_cost
    policy = policy or AdaptivePolicy(workers)
    records = [None] * len(candidates)
    batches = {}; order = []
    for index, (side, path) in enumerate(candidates):
        check_cancel(cancel)
        try:
            before = signature(path)
            if before not in batches:
                batches[before] = []; order.append(before)
            batches[before].append((index, side, path))
        except Exception as error:
            records[index] = (side, path, None, None, error)
    done = sum(r is not None for r in records); pending = {}; cursor = 0
    estimates = {}
    progress(done, len(records), 'Preparing automatic comparison…')

    slots = {}
    slot_lock = threading.Lock()

    def decode(side, path, before):
        with slot_lock:
            slot = slots.setdefault(threading.get_ident(), len(slots) + 1)
        if activity: activity(slot, side, path)
        try:
            return decode_file(path, before)
        finally:
            if activity: activity(slot, '', '')

    def decode_file(path, before):
        check_cancel(cancel)
        if signature(path) != before: raise ValueError('File changed before scanning')
        started = time.monotonic()
        with decoding_budget(): key = fingerprint(path, cancel)
        if signature(path) != before: raise ValueError('File changed during scanning')
        check_cancel(cancel)
        return key, time.monotonic() - started

    pool = ThreadPoolExecutor(max_workers=policy.maximum, thread_name_prefix='Mahogany-media')
    try:
        while cursor < len(order) or pending:
            check_cancel(cancel)
            while cursor < len(order):
                before = order[cursor]; path = batches[before][0][2]
                if before not in estimates: estimates[before] = estimate(path)
                cost, kind = estimates[before]
                if not policy.can_start(cost, kind, [(c, k) for _, c, k in pending.values()]): break
                future = pool.submit(decode, batches[before][0][1], path, before)
                pending[future] = (before, cost, kind); cursor += 1
                progress(done, len(records), f'Checking files · {len(pending)} simultaneous comparisons')
            completed, _ = wait(pending, timeout=.1, return_when=FIRST_COMPLETED)
            for future in completed:
                before, _, _ = pending.pop(future)
                error = None; key = None
                try:
                    key, elapsed = future.result(); policy.finished(elapsed)
                except Exception as caught:
                    check_cancel(cancel); error = caught
                for index, side, path in batches[before]:
                    records[index] = (side, path, before, key, error); done += 1
                progress(done, len(records), f'Checked {done} of {len(records)} files · {len(pending)} active')
        check_cancel(cancel)
        return records
    finally:
        for future in pending: future.cancel()
        # Running checks own their resources and finish before the scan reports stopped.
        pool.shutdown(wait=True, cancel_futures=True)
