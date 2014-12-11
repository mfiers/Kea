
import leip
import logging
import subprocess as sp

import jinja2

lg = logging.getLogger(__name__)


@leip.hook('pre_argparse')
def define_args(app):
    maildef = app.conf['plugin.mail.default']
    if maildef:
        app.parser.add_argument('-M', '--no_mail', help='do NOT send an email report', action='store_true')
    else:
        app.parser.add_argument('-m', '--mail', help='send an email report', action='store_true')
    mailsuc = app.conf['plugin.mail.on_success']
    if mailsuc:
        app.parser.add_argument('-U', '--no_mail_on_success', dest='mail_on_success',
                                help='do NOT send an email report on successful execution',
                                action='store_false')
    else:
        app.parser.add_argument('-u', '--mail_on_success', help='send an email report on ' +
                                'successful execution', action='store_true')

        
HTML_MESSAGE = """MIME-Version: 1.0
Content-Type: text/html;
Subject: 
{%- if success %} Kea/Ok: {{cl50}} 
{%- else %} Kea/Fail: {{ cl50 }} 
{%- endif %}


{% if success -%}
<h2 style='color:green'>Kea/Job OK</h2>
{%- else -%}
<h2 style='color:red'>Kea/Job FAIL</h2>
{%- endif %}

{% if all_jinf|length > 1 -%}
<h3>Template Command Line</h3>
<pre>
  {{ clj }}
</pre>

<h3>Actual command lines</h3>
{%- else -%}
<h3>Command line</h3>{% endif %}

<pre>{% for jinf in all_jinf -%}
{{ jinf.run_no }}.  {{ jinf['cl']|join(" ") }}

{% endfor %}
</pre>
{%- if all_jinf|length > 1 %}
<h3>Run stats</h3>
 
<table>
<tr>
  <th>No.</th>
{% if not success %}
  <th>rc</th>
{% endif %}
  <th>Run time</th>
  <th>Cpu time</th>
  <th>Peak mem</th>
  <th>Stdout</th>
  <th>Stderr</th>
</tr>
{% for jinf in all_jinf %}
<tr>
  <td><b>{{ jinf.run_no }}</b></td>
  {%- if not success %}{% if jinf.returncode == 0 %}
  <td><span style='color:green'>0</span></td>
  {% else %}
  <td><span style='color:red;weight:bold;'>{{jinf.returncode}}</span></td>
  {%- endif %}{% endif %}
  <td>{{ jinf.runtime }}</td>
  <td>{{ "%.3f"|format(jinf.ps_cputime_user) }}</td>
  <td>{{ "%d"|format(jinf.ps_meminfo_max_rss) }}</td>
  <td>{{ jinf.stdout_len }}</td>
  <td>{{ jinf.stderr_len }}</td>
</tr>
{%- endfor %}
</table>
{% endif %}

{% for jinf in all_jinf %}
<h3>Full run report {% if all_jinf|length > 1 %} ({{ jinf.run_no }}) {% endif %}</h3>
<table>
{% for k in jinf %}
<tr {% if loop.cycle(False, True) -%}style="background-color: #EEEEEE;"
    {%- endif %}><th style="text-align: left;">{{k}}</th>
    {%- if k == "cl" %}
      <span style="font-family:Lucida Console,Bitstream Vera Sans Mono,Courier New,monospace;">{{ " ".join(jinf.cl) }}</span>
    {%- else %}
    <td>{{ jinf[k] }}</td>
    {%- endif %}
</tr>
{%- endfor %}
</table>

{% endfor %}

"""

@leip.hook('finish')
def mail(app):

    if not hasattr(app, 'all_jinf'):
        return
    
    maildef = app.conf['plugin.mail.default']
    mailsuc = app.conf['plugin.mail.on_success']

    #did all jobs finish successfully?
    success = True
    
    for jinf in app.all_jinf:
        if jinf['returncode'] != 0:
            success = False
            break

    data = {}
    data['success'] = success
    data['all_jinf'] = app.all_jinf
    data['app'] = app
    data['clj50'] = " ".join(app.cl)[:50]
    data['clj'] = " ".join(app.cl)

    
    if success and not app.args.mail_on_success:
        #all is well - do not send an email
        return

    # mkea conf set plugin.mail.recipient 'mark.fiers@cme.vib-kuleuven.be'
    mailto = app.conf['plugin.mail.recipient']
    
    if not mailto:
        lg.warning("No mail recipient defined - cannot send mail")
        return
    

    message = jinja2.Template(HTML_MESSAGE)
    message = message.render(data)

    p = sp.Popen("sendmail %s" % mailto, stdin=sp.PIPE, shell=True)
    p.communicate(message.encode('utf-8'))


    exit(p.returncode)
