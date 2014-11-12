config_opts.setdefault('plugin_conf', {})
config_opts['plugin_conf']['ccache_enable'] = False
config_opts['root'] = '{{ name }}'
config_opts['target_arch'] = 'x86_64'
config_opts['legal_host_arches'] = ('x86_64',)
config_opts['chroot_setup_cmd'] = 'groupinstall base development'
config_opts['dist'] = 'el6'  # only useful for --resultdir variable subst

config_opts['yum.conf'] = """
[main]
cachedir=/var/cache/yum
debuglevel=1
reposdir=/dev/null
logfile=/var/log/yum.log
retries=20
obsoletes=1
gpgcheck=0
assumeyes=1
syslog_ident=mock
syslog_device=

# repos
[core]
name=core
baseurl=http://10.2.0.2/cobbler/ks_mirror/CentOS6.5-x86_64
priority=100

{% for repo in repos %}
[{{ repo.name }}]
name={{ repo.name }}
baseurl={{ repo.url }}
priority={{ repo.priority }}
{% endfor %}
"""
