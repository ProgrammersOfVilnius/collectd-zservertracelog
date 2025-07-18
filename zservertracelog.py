#!/usr/bin/env python3

import datetime
import itertools
import optparse
import os
import sys
import time


# Code bellow are taken from zservertracelog/zc/tracereport.py
# ------------------------8<----------------------------------
def seconds_difference(dt1, dt2):
    delta = dt1 - dt2
    return delta.seconds + delta.microseconds * 1e-6


def parse_line(line):
    parts = line.split(' ', 4)
    code, rid, rdate, rtime = parts[:4]
    if len(parts) > 4:
        msg = parts[4]
    else:
        msg = ''
    return (code, rid, rdate + ' ' + rtime, msg)


def parse_datetime(s):
    # XXX this chokes on tracelogs with the 'T' time separator.
    date, t = s.split(' ')
    try:
        h_m_s, ms = t.split('.')
    except ValueError:
        h_m_s = t.strip()
        ms = '0'
    args = [int(arg) for arg in (date.split('-') + h_m_s.split(':') + [ms])]
    return datetime.datetime(*args)


class Request(object):

    output_bytes = '-'

    def __init__(self, start, method, url):
        self.method = method
        self.url = url
        self.start = start
        self.state = 'input'

    def I(self, input_time, input_bytes):
        self.input_time = input_time
        self.input_bytes = input_bytes
        self.state = 'wait'

    def C(self, start_app_time):
        self.start_app_time = start_app_time
        self.state = 'app'

    def A(self, app_time, response, output_bytes):
        self.app_time = app_time
        self.response = response
        self.output_bytes = output_bytes
        self.state = 'output'

    def E(self, end):
        self.end = end

    @property
    def app_seconds(self):
        return seconds_difference(self.app_time, self.start_app_time)

    @property
    def total_seconds(self):
        return seconds_difference(self.end, self.start)
# ------------------------>8----------------------------------


def readrequests(tail):
    requests = {}
    for line in tail.readlines():
        typ, rid, strtime, msg = parse_line(line)
        dt = parse_datetime(strtime)

        # Request begins
        if typ == 'B':
            if rid in requests:
                request = requests[rid]

            method, url = msg.split(' ', 1)
            request = Request(dt, method, url.strip())
            requests[rid] = request

        # Got request input
        elif typ == 'I':
            if rid in requests:
                requests[rid].I(dt, line[3])

        # Entered application thread
        elif typ == 'C':
            if rid in requests:
                requests[rid].C(dt)

        # Database activity
        elif typ == 'D':
            pass  # ignore db stats for now

        # Application done
        elif typ == 'A':
            if rid in requests:
                try:
                    response_code, bytes_len = msg.split()
                except ValueError:
                    response_code = '500'
                    bytes_len = len(msg)
                requests[rid].A(dt, response_code, bytes_len)

        # Request done
        elif typ == 'E':
            if rid in requests:
                request = requests.pop(rid)
                request.E(dt)
                yield (rid, request)

        # Server startup
        elif typ in 'SX':
            requests = {}

        # Unknow log line
        else:
            print('WTF: %s' % line)


class Tail(object):
    def __init__(self, filename, seek=True, wait=True, interval=60):
        self.filename = filename
        self.fh = None
        self.fsize = os.path.getsize(filename)
        self.seek = seek
        self.wait = wait
        self.interval = interval

    def reopen(self):
        fsize = os.path.getsize(self.filename)
        if self.fh is None:
            self.fh = open(self.filename)
            if self.seek:
                self.fh.seek(0, os.SEEK_END)
        elif fsize < self.fsize:
            # Seek to begining if file was truncated
            self.fh.seek(0)
        self.fsize = fsize

    def readlines(self):
        while True:
            self.reopen()
            line = self.fh.readline()
            if not line:
                sys.stdout.flush()
                if self.wait:
                    time.sleep(self.interval)
                    continue
                else:
                    break
            yield line


def timestamp(d):
    return int(time.mktime(d.timetuple()))


def putval(template, context, t, fields, data):
    values = []
    for name, item in itertools.zip_longest(fields, data):
        cnt, sum_, min_, max_ = item
        avg = sum_ / cnt
        values.append('%f:%f:%f' % (avg, min_, max_))
    values = ':'.join(values)
    print(template % dict(context, timestamp=t, value=values))


def update_fields(values, data):
    new = []
    for value, item in itertools.zip_longest(values, data):
        cnt, sum_, min_, max_ = item
        new.append((
            cnt + 1,
            sum_ + value,
            min(min_, value) or value,
            max(max_, value),
        ))
    return new


def reset_fields(values):
    new = []
    cnt, sum_, min_, max_ = 0, 0.0, 0.0, 0.0
    for value in values:
        new.append((cnt, sum_, min_, max_))
    return new


def main():
    """
    This script is intended to be used as collectd plugin.
    """
    usage = "usage: %prog [options] TRACELOGFILE INSTANCENAME"
    parser = optparse.OptionParser(usage, description=main.__doc__)
    parser.add_option("--no-seek",
                      dest="seek", action="store_false", default=True,
                      help="read file from start, do not seek to end of file")
    parser.add_option("--no-wait",
                      dest="wait", action="store_false", default=True,
                      help="do not wait for new lines in file")
    parser.add_option("-i", "--interval", metavar="SECONDS",
                      dest="interval", action="store", default=10,
                      help="read new lines by specified interval")
    parser.add_option("--hostname",
                      dest="hostname", action="store", default=os.uname()[1],
                      help="hostname")

    (options, args) = parser.parse_args()

    if len(args) != 2:
        parser.error("incorrect number of arguments")

    logfile = args[0]
    instance = args[1]

    template = ' '.join([
        'PUTVAL',
        '%(hostname)s/%(plugin)s/%(type)s-%(instance)s',
        'interval=%(interval)d',
        '%(timestamp)d:%(value)s',
    ])
    context = dict(
        hostname=os.environ.get('COLLECTD_HOSTNAME', options.hostname),
        interval=float(os.environ.get('COLLECTD_INTERVAL', options.interval)),
        plugin='zservertracelog',
        type='zoperequest',
        instance=instance,
    )

    interval = context['interval']
    tail = Tail(logfile, interval=interval, seek=options.seek,
                wait=options.wait)
    last_timestamp = None
    fields = ('req', 'app')
    data = reset_fields(fields)
    for rid, request in readrequests(tail):
        t = timestamp(request.start)
        last_timestamp = last_timestamp or t
        values = (request.total_seconds, request.app_seconds)
        if t - last_timestamp >= interval:
            putval(template, context, last_timestamp, fields, data)
            data = reset_fields(fields)
            last_timestamp = t

        data = update_fields(values, data)

    if last_timestamp and t > last_timestamp:
        putval(template, context, last_timestamp, fields, data)


if __name__ == '__main__':
    main()
