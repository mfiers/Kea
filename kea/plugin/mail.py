"""
Send mail plugin


"""

import leip
import logging
import subprocess as sp

import jinja2

import kea.utils

lg = logging.getLogger(__name__)


@leip.hook('pre_argparse')
def define_args(app):
    mail_group = app.parser.add_argument_group('Mail plugin')

    mail_group.add_argument('--mail_send', help='Send an email report',
                            action='store_true', default=None)
    
    mail_group.add_argument('-m', '--mail_on_success', 
                            help='Also send an email when a job finishes succesfully',
                            action='store_true', default=None)

    mail_group.add_argument('--mail_recipient', 
                            help='email address to send report to (comma ' +
                            'separate multiple addresses)',
                            action='store_true', default=None)

        
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
    {%- endif %}><th style="text-align: left; vertical-align: text-top;">{{k}}</th>
    {{ jinf[k]|pretty(k) }}
</tr>
{%- endfor %}
</table>

{% endfor %}

"""

@leip.hook('finish')
def mail(app):

    #lg.setLevel(logging.DEBUG)
    if not hasattr(app, 'all_jinf'):
        return

    maildef = app.defargs.get('send_mail')
    mailsuc = app.defargs.get('mail_on_success')
    mailrecip = app.defargs.get('mail_recipient')


    if not maildef:
        lg.debug("no mail to be send")
        #sending mail is not required
        return

    #did all jobs finish successfully?
    success = True
    
    for jinf in app.all_jinf:
        if jinf['returncode'] != 0:
            success = False
            break

    if not mailsuc and success:
        lg.debug("job finished successfully - not sending mail")
        return
        
    data = {}
    data['success'] = success
    data['all_jinf'] = app.all_jinf
    data['app'] = app
    data['clj50'] = " ".join(app.cl)[:50]
    data['clj'] = " ".join(app.cl)

    
    if not mailrecip:
        lg.debug("No mail recipient(s) defined - cannot send mail")
        return

    def keapretty(value, key):
        return kea.utils.make_pretty_kv_html(key, value)

    env = jinja2.Environment()
    env.filters['pretty'] = keapretty
    template = env.from_string(HTML_MESSAGE)
    
    message = template.render(data)

    if ',' in mailrecip:
        mailrecip = " ".join(mailrecip.split(','))

    lg.debug("Sending report mail to: %s", mailrecip)
                             
    p = sp.Popen("sendmail %s" % mailrecip, stdin=sp.PIPE, shell=True)
    p.communicate(message.encode('utf-8'))


    exit(p.returncode)
