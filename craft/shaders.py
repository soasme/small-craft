"""The block and sky shaders, in GLSL 3.30 as raylib's desktop OpenGL
takes it. raylib names the attributes; texture0 and texture1 are the two
textures draw_mesh binds."""

BLOCK_VERTEX = """#version 330
uniform mat4 matrix;
uniform vec3 camera;
uniform float fog_distance;
uniform int ortho;

in vec3 vertexPosition;
in vec3 vertexNormal;
in vec2 vertexTexCoord;
in vec2 vertexTexCoord2;  // ambient occlusion, light

out vec2 fragment_uv;
out float fragment_ao;
out float fragment_light;
out float fog_factor;
out float fog_height;
out float diffuse;

const float pi = 3.14159265;
const vec3 light_direction = normalize(vec3(-1.0, 1.0, -1.0));

void main() {
    vec4 position = vec4(vertexPosition, 1.0);
    gl_Position = matrix * position;
    fragment_uv = vertexTexCoord;
    fragment_ao = 0.3 + (1.0 - vertexTexCoord2.x) * 0.7;
    fragment_light = vertexTexCoord2.y;
    diffuse = max(0.0, dot(vertexNormal, light_direction));
    if (bool(ortho)) {
        fog_factor = 0.0;
        fog_height = 0.0;
    }
    else {
        float camera_distance = distance(camera, vec3(position));
        fog_factor = pow(clamp(camera_distance / fog_distance, 0.0, 1.0), 4.0);
        float dy = position.y - camera.y;
        float dx = distance(position.xz, camera.xz);
        fog_height = (atan(dy, dx) + pi / 2) / pi;
    }
}
"""

BLOCK_FRAGMENT = """#version 330
uniform sampler2D texture0;  // the block atlas
uniform sampler2D texture1;  // the sky
uniform float timer;
uniform float daylight;
uniform int ortho;

in vec2 fragment_uv;
in float fragment_ao;
in float fragment_light;
in float fog_factor;
in float fog_height;
in float diffuse;

out vec4 finalColor;

void main() {
    vec3 color = vec3(texture(texture0, fragment_uv));
    if (color == vec3(1.0, 0.0, 1.0)) {
        discard;
    }
    bool cloud = color == vec3(1.0, 1.0, 1.0);
    if (cloud && bool(ortho)) {
        discard;
    }
    float df = cloud ? 1.0 - diffuse * 0.2 : diffuse;
    float ao = cloud ? 1.0 - (1.0 - fragment_ao) * 0.2 : fragment_ao;
    ao = min(1.0, ao + fragment_light);
    df = min(1.0, df + fragment_light);
    float value = min(1.0, daylight + fragment_light);
    vec3 light_color = vec3(value * 0.3 + 0.2);
    vec3 ambient = vec3(value * 0.3 + 0.2);
    vec3 light = ambient + light_color * df;
    color = clamp(color * light * ao, vec3(0.0), vec3(1.0));
    vec3 sky_color = vec3(texture(texture1, vec2(timer, fog_height)));
    color = mix(color, sky_color, fog_factor);
    finalColor = vec4(color, 1.0);
}
"""

SKY_VERTEX = """#version 330
uniform mat4 matrix;

in vec3 vertexPosition;
in vec2 vertexTexCoord;

out vec2 fragment_uv;

void main() {
    gl_Position = matrix * vec4(vertexPosition, 1.0);
    fragment_uv = vertexTexCoord;
}
"""

SKY_FRAGMENT = """#version 330
uniform sampler2D texture0;
uniform float timer;

in vec2 fragment_uv;

out vec4 finalColor;

void main() {
    finalColor = texture(texture0, vec2(timer, fragment_uv.t));
}
"""
