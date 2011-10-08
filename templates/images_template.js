[
	{% for screen in screenshots %}
	{% templatetag openbrace %}
		timestamp : '{{ screen.3 }}',
		full : 'images/{{ screen.2|urlencode }}',
		thumb : 'square/{{ screen.2|urlencode }}',
		userlink : '<a href="http://twitter.com/{{ screen.0|escape }}">@{{ screen.0|escape }}</a>',
		imageinfo : '{{ screen.1|escape|linebreaksbr|urlize }}',
	{% templatetag closebrace %},
	{% endfor %}
]