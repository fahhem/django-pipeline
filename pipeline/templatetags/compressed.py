from pipeline.storage import default_storage

from django import template
from django.template.loader import render_to_string

from pipeline.conf import settings
from pipeline.packager import Packager, PackageNotFound
from pipeline.utils import guess_type, path_is_url

register = template.Library()

class CommonNode(template.Node):
    def __init__(self, name):
        self.name = name

    def render(self, context):
        package_name = template.Variable(self.name).resolve(context)
        package = self.packages.get(package_name, {})
        if package:
            package = {package_name: package}
        self.packager = Packager(css_packages=package, js_packages=package)

        try:
            package = self.packager.package_for(self.type, package_name)
        except PackageNotFound:
            return ''  # fail silently, do not return anything if an invalid group is specified

        if settings.PIPELINE:
            return self.render_type_specific(package, package.output_filename)
        else:
            paths = self.packager.compile(package.paths)
            return self.render_individual(package, paths)

    def render_individual(self, package, paths):
        tags = [self.render_type_specific(package, path) for path in paths]
        return '\n'.join(tags)

    def get_url(self, path):
        if path_is_url(path):
            return path
        return default_storage.url(path)

class CompressedCSSNode(CommonNode):
    def __init__(self, name):
        super(CompressedCSSNode, self).__init__(name)
        self.packages = settings.PIPELINE_CSS
        self.type = 'css'

    def render_css(self, package, path):
        template_name = package.template_name or "pipeline/css.html"
        context = package.extra_context
        context.update({
            'type': guess_type(path, 'text/css'),
            'url': self.get_url(path)
        })
        return render_to_string(template_name, context)
    render_type_specific = render_css

class CompressedJSNode(CommonNode):
    def __init__(self, name):
        super(CompressedJSNode, self).__init__(name)
        self.packages = settings.PIPELINE_JS
        self.type = 'js'

    def render_js(self, package, path):
        template_name = package.template_name or "pipeline/js.html"
        context = package.extra_context
        context.update({
            'type': guess_type(path, 'text/javascript'),
            'url': self.get_url(path)
        })
        return render_to_string(template_name, context)

    render_type_specific = render_js

    def render_inline(self, package, js):
        context = package.extra_context
        context.update({
            'source': js
        })
        return render_to_string("pipeline/inline_js.html", context)

    def render_individual(self, package, paths, templates=None):
        tags = []
        if templates:
            tags.append(self.render_inline(package, templates))
        return super(CompressedJSNode, self).render_individual(package, paths) + '\n'.join(tags)


def common_compressed(parser, token, node_class):
    try:
        tag_name, name = token.split_contents()
    except ValueError:
        raise template.TemplateSyntaxError, '%r requires exactly one argument: the name of a group in the PIPELINE_CSS setting' % token.split_contents()[0]
    return node_class(name)

@register.tag
def compressed_css(parser, token):
    return common_compressed(parser, token, CompressedCSSNode)

@register.tag
def compressed_js(parser, token):
    return common_compressed(parser, token, CompressedJSNode)

