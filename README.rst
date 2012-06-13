Configureation
==============

Setup collectd
--------------

Add these lines to ``/etc/collectd/collectd.conf``::

    TypesDB "/usr/share/collectd/types.db" "/PLUGIN_PATH/types.db"
    LoadPlugin exec
    <Plugin rrdtool>
      DataDir "/var/lib/collectd/rrd"
    </Plugin>
    <Plugin exec>
      Exec nobody "/PLUGIN_PATH/zservertracelog.py" "/path/to/trace.log" "instance_name"
    </Plugin>

Replace ``PLUGIN_PATH`` to path of this repository on server.

Also you can change nobody to user, that can access ``trace.log`` file.

Restart collectd::

    sudo service collectd restart

Setup collection.cgi
--------------------

Add this code snippet to ``collection.cgi``, in ``$GraphDefs`` hash::

    zoperequest => [
        '-v',
        's',
        'DEF:reqavg={file}:reqavg:AVERAGE',
        'DEF:reqmin={file}:reqmin:MIN',
        'DEF:reqmax={file}:reqmax:MAX',
        'DEF:appavg={file}:appavg:AVERAGE',
        'DEF:appmin={file}:appmin:MIN',
        'DEF:appmax={file}:appmax:MAX',
        "AREA:reqmax#$HalfBlue",
        "AREA:reqmin#$Canvas",
        "AREA:appmax#$HalfRed",
        "AREA:appmin#$Canvas",
        "LINE1:reqavg#$FullBlue:Total     ",
        'GPRINT:reqmin:MIN:%5.1lf%s Min,',
        'GPRINT:reqavg:AVERAGE:%5.1lf%s Avg,',
        'GPRINT:reqmax:MAX:%5.1lf%s Max\l',
        "LINE1:appavg#$FullRed:Processing",
        'GPRINT:appmin:MIN:%5.1lf%s Min,',
        'GPRINT:appavg:AVERAGE:%5.1lf%s Avg,',
        'GPRINT:appmax:MAX:%5.1lf%s Max\l',
    ],

``collection.cgi`` file can be found in
``/usr/share/doc/collectd-core/examples/collection.cgi``.
