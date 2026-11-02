/* The raylib host for Small Craft. The game is Python: smallcraft.py and
 * the craft package. This file registers three C modules, as a QuickJS
 * host registers them with JS_NewCModule:
 *
 *   raylib  windows, input, textures, shaders, meshes and 2-D drawing;
 *   noise   fractal simplex noise (noise.c);
 *   libm    the C library's trigonometry.
 *
 * The game builds every vertex and matrix itself; the host only uploads
 * them to the GPU. spyc bundles the Python and the textures, so the program
 * needs no file beside it. It mounts the working directory so the game can
 * save the world to craft.txt. */
#include "spy.h"
#include "host.h"
#include "noise.h"

#include <math.h>
#include <raylib.h>
#include <rlgl.h>
#include <stdarg.h>
#ifdef __EMSCRIPTEN__
#include <emscripten.h>
#include <emscripten/html5.h>
#endif

/* Convert positional arguments by format: 'n' number (double), 'i' integer,
 * 's' string, 'c' color, an (r, g, b) or (r, g, b, a) sequence of integers. */
static int args(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, const char *format, ...) {
    if (kw || argc != strlen(format)) { spy_error(c, "TypeError", "wrong number of arguments"); return -1; }
    va_list out;
    va_start(out, format);
    int status = 0;
    for (size_t i = 0; !status && i < argc; i++) {
        if (format[i] == 'n') status = spy_as_float(c, argv[i], va_arg(out, double *));
        else if (format[i] == 'i') {
            int64_t x;
            int *to = va_arg(out, int *);
            status = spy_as_int(c, argv[i], &x);
            if (!status && (x < INT32_MIN || x > INT32_MAX)) { spy_error(c, "OverflowError", "integer out of range"); status = 1; }
            *to = (int)x;
        }
        else if (format[i] == 's') status = !(*va_arg(out, const char **) = spy_as_string(c, argv[i], NULL));
        else {
            Color *color = va_arg(out, Color *);
            unsigned char rgba[4] = {0, 0, 0, 255};
            SPYValue *it = spy_iter(c, argv[i]), *v;
            size_t n = 0;
            status = !it;
            while (!status && (v = spy_next(c, it))) {
                int64_t x;
                status = n == 4 || spy_as_int(c, v, &x) || x < 0 || x > 255;
                if (!status) rgba[n++] = (unsigned char)x;
                spy_release(v);
            }
            if (!status && (spy_error_type(c)[0] || n < 3)) status = 1;
            if (status && !spy_error_type(c)[0]) spy_error(c, "ValueError", "color must be 3 or 4 integers in 0..255");
            spy_release(it);
            *color = (Color){rgba[0], rgba[1], rgba[2], rgba[3]};
        }
    }
    va_end(out);
    return status ? -1 : 0;
}

/* Read a sequence of numbers into a new float array; *count is its length. */
static float *floats(SPYContext *c, SPYValue *sequence, size_t *count) {
    SPYValue *it = spy_iter(c, sequence), *v;
    if (!it) return NULL;
    size_t n = 0, cap = 1024;
    float *data = malloc(cap * sizeof *data);
    while (data && (v = spy_next(c, it))) {
        double x;
        int bad = spy_as_float(c, v, &x);
        spy_release(v);
        if (bad) break;
        if (n == cap) {
            float *more = realloc(data, (cap *= 2) * sizeof *data);
            if (!more) { free(data); data = NULL; break; }
            data = more;
        }
        data[n++] = (float)x;
    }
    spy_release(it);
    if (!data) { spy_error(c, "MemoryError", "out of memory"); return NULL; }
    if (spy_error_type(c)[0]) { free(data); return NULL; }
    *count = n;
    return data;
}

/* A 4x4 matrix given column by column, as OpenGL takes it. */
static Matrix to_matrix(const float *a) {
    return (Matrix){a[0], a[4], a[8], a[12], a[1], a[5], a[9], a[13], a[2], a[6], a[10], a[14], a[3], a[7], a[11], a[15]};
}

/* GPU resources the game loaded, named by their index in these tables. */
static Texture2D textures[8];
static size_t texture_count;
static Shader shaders[8];
static size_t shader_count;
static Mesh *meshes;
static size_t mesh_count;

static SPYValue *init_window(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, void *data) {
    (void)data; double w, h; const char *title;
    if (args(c, argc, argv, kw, "nns", &w, &h, &title)) return NULL;
#ifdef __EMSCRIPTEN__
    /* In a page the canvas fills its frame (an X card, say): start at the
     * size the page gave it; raylib follows later resizes. */
    emscripten_get_element_css_size("#canvas", &w, &h);
#endif
    SetConfigFlags(FLAG_VSYNC_HINT | FLAG_WINDOW_RESIZABLE);
    InitWindow((int)w, (int)h, title);
    SetExitKey(KEY_NULL);
    return spy_none(c);
}
static SPYValue *close_window(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, void *data) {
    (void)data;
    if (args(c, argc, argv, kw, "")) return NULL;
    for (size_t i = 0; i < mesh_count; i++) if (meshes[i].vaoId) UnloadMesh(meshes[i]);
    free(meshes); meshes = NULL; mesh_count = 0;
    while (shader_count) UnloadShader(shaders[--shader_count]);
    while (texture_count) UnloadTexture(textures[--texture_count]);
    CloseWindow();
    return spy_none(c);
}
/* run(frame): call frame() once a frame. On the desktop it returns True
 * when the window closes. A browser runs the frames itself, between its
 * own events, so on the web it returns False at once and frame runs later
 * from emscripten's main loop (until it raises). */
#ifdef __EMSCRIPTEN__
static SPYContext *web_context;
static SPYValue *web_frame;
static void web_loop(void) {
    SPYValue *result = spy_call(web_context, web_frame, 0, NULL);
    if (!result) { host_exit_status(web_context); emscripten_cancel_main_loop(); }
    spy_release(result);
}
#endif
static SPYValue *run(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, void *data) {
    (void)data;
    if (kw || argc != 1) return spy_error(c, "TypeError", "run takes a function");
#ifdef __EMSCRIPTEN__
    web_context = c;
    web_frame = spy_retain(argv[0]);
    emscripten_set_main_loop(web_loop, 0, 0);
    return spy_bool(c, 0);
#else
    while (!WindowShouldClose()) {
        SPYValue *result = spy_call(c, argv[0], 0, NULL);
        if (!result) return NULL;
        spy_release(result);
    }
    return spy_bool(c, 1);
#endif
}
static SPYValue *get_time(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, void *data) {
    (void)data;
    return args(c, argc, argv, kw, "") ? NULL : spy_float(c, GetTime());
}
static SPYValue *get_fps(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, void *data) {
    (void)data;
    return args(c, argc, argv, kw, "") ? NULL : spy_int(c, GetFPS());
}
static SPYValue *get_screen_size(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, void *data) {
    (void)data;
    if (args(c, argc, argv, kw, "")) return NULL;
    SPYValue *size[2] = {spy_int(c, GetRenderWidth()), spy_int(c, GetRenderHeight())};
    SPYValue *result = size[0] && size[1] ? spy_tuple(c, 2, size) : NULL;
    spy_release(size[0]); spy_release(size[1]);
    return result;
}
static SPYValue *is_key_down(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, void *data) {
    (void)data; int key;
    return args(c, argc, argv, kw, "i", &key) ? NULL : spy_bool(c, IsKeyDown(key));
}
static SPYValue *is_key_pressed(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, void *data) {
    (void)data; int key;
    return args(c, argc, argv, kw, "i", &key) ? NULL : spy_bool(c, IsKeyPressed(key) || IsKeyPressedRepeat(key));
}
/* The next character typed this frame, or "" when there is none. */
static SPYValue *get_char_pressed(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, void *data) {
    (void)data;
    if (args(c, argc, argv, kw, "")) return NULL;
    int size, code = GetCharPressed();
    const char *text = code ? CodepointToUTF8(code, &size) : "";
    return spy_string(c, text, code ? (size_t)size : 0);
}
static SPYValue *is_mouse_button_pressed(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, void *data) {
    (void)data; int button;
    return args(c, argc, argv, kw, "i", &button) ? NULL : spy_bool(c, IsMouseButtonPressed(button));
}
static SPYValue *is_mouse_button_down(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, void *data) {
    (void)data; int button;
    return args(c, argc, argv, kw, "i", &button) ? NULL : spy_bool(c, IsMouseButtonDown(button));
}
static SPYValue *is_mouse_button_released(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, void *data) {
    (void)data; int button;
    return args(c, argc, argv, kw, "i", &button) ? NULL : spy_bool(c, IsMouseButtonReleased(button));
}
/* get_touches(): the fingers on the screen, as (id, x, y) tuples. */
static SPYValue *get_touches(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, void *data) {
    (void)data;
    if (args(c, argc, argv, kw, "")) return NULL;
    SPYValue *list = spy_list(c);
    for (int i = 0; list && i < GetTouchPointCount(); i++) {
        Vector2 at = GetTouchPosition(i);
        SPYValue *parts[3] = {spy_int(c, GetTouchPointId(i)), spy_float(c, at.x), spy_float(c, at.y)};
        SPYValue *touch = parts[0] && parts[1] && parts[2] ? spy_tuple(c, 3, parts) : NULL;
        if (!touch || spy_list_append(c, list, touch)) { spy_release(list); list = NULL; }
        spy_release(touch);
        for (int k = 0; k < 3; k++) spy_release(parts[k]);
    }
    return list;
}
static SPYValue *get_mouse_delta(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, void *data) {
    (void)data;
    if (args(c, argc, argv, kw, "")) return NULL;
    Vector2 d = GetMouseDelta();
    SPYValue *xy[2] = {spy_float(c, d.x), spy_float(c, d.y)};
    SPYValue *result = xy[0] && xy[1] ? spy_tuple(c, 2, xy) : NULL;
    spy_release(xy[0]); spy_release(xy[1]);
    return result;
}
static SPYValue *get_mouse_wheel_move(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, void *data) {
    (void)data;
    return args(c, argc, argv, kw, "") ? NULL : spy_float(c, GetMouseWheelMove());
}
static SPYValue *disable_cursor(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, void *data) {
    (void)data;
    if (args(c, argc, argv, kw, "")) return NULL;
    DisableCursor();
    return spy_none(c);
}
static SPYValue *enable_cursor(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, void *data) {
    (void)data;
    if (args(c, argc, argv, kw, "")) return NULL;
    EnableCursor();
    return spy_none(c);
}
static SPYValue *is_cursor_hidden(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, void *data) {
    (void)data;
    return args(c, argc, argv, kw, "") ? NULL : spy_bool(c, IsCursorHidden());
}
static SPYValue *begin_drawing(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, void *data) {
    (void)data;
    if (args(c, argc, argv, kw, "")) return NULL;
    BeginDrawing();
    return spy_none(c);
}
static SPYValue *end_drawing(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, void *data) {
    (void)data;
    if (args(c, argc, argv, kw, "")) return NULL;
    EndDrawing();
    return spy_none(c);
}
static SPYValue *clear_background(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, void *data) {
    (void)data; Color color;
    if (args(c, argc, argv, kw, "c", &color)) return NULL;
    ClearBackground(color);
    return spy_none(c);
}
static SPYValue *draw_rectangle(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, void *data) {
    (void)data; double x, y, w, h; Color color;
    if (args(c, argc, argv, kw, "nnnnc", &x, &y, &w, &h, &color)) return NULL;
    DrawRectangleRec((Rectangle){(float)x, (float)y, (float)w, (float)h}, color);
    return spy_none(c);
}
static SPYValue *draw_circle(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, void *data) {
    (void)data; double x, y, r; Color color;
    if (args(c, argc, argv, kw, "nnnc", &x, &y, &r, &color)) return NULL;
    DrawCircleV((Vector2){(float)x, (float)y}, (float)r, color);
    return spy_none(c);
}
static SPYValue *draw_text(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, void *data) {
    (void)data; const char *text; double x, y, size; Color color;
    if (args(c, argc, argv, kw, "snnnc", &text, &x, &y, &size, &color)) return NULL;
    DrawText(text, (int)x, (int)y, (int)size, color);
    return spy_none(c);
}
static SPYValue *measure_text(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, void *data) {
    (void)data; const char *text; double size;
    return args(c, argc, argv, kw, "sn", &text, &size) ? NULL : spy_int(c, MeasureText(text, (int)size));
}

/* load_texture(png, smooth): a texture from PNG bytes, clamped at its edges,
 * filtered linearly when smooth and to the nearest texel otherwise. Its rows
 * are flipped, so v runs from the bottom of the image to its top. */
static SPYValue *load_texture(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, void *data) {
    (void)data; size_t size;
    if (kw || argc != 2) return spy_error(c, "TypeError", "load_texture takes PNG bytes and a flag");
    const unsigned char *png = spy_as_bytes(c, argv[0], &size);
    if (!png) return NULL;
    if (texture_count == sizeof textures / sizeof *textures) return spy_error(c, "RuntimeError", "too many textures");
    Image image = LoadImageFromMemory(".png", png, (int)size);
    if (!image.data) return spy_error(c, "ValueError", "not a PNG image");
    ImageFlipVertical(&image);
    Texture2D texture = LoadTextureFromImage(image);
    UnloadImage(image);
    SetTextureFilter(texture, spy_truth(argv[1]) ? TEXTURE_FILTER_BILINEAR : TEXTURE_FILTER_POINT);
    SetTextureWrap(texture, TEXTURE_WRAP_CLAMP);
    textures[texture_count] = texture;
    return spy_int(c, (int64_t)texture_count++);
}
static SPYValue *load_shader(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, void *data) {
    (void)data; const char *vertex, *fragment;
    if (args(c, argc, argv, kw, "ss", &vertex, &fragment)) return NULL;
    if (shader_count == sizeof shaders / sizeof *shaders) return spy_error(c, "RuntimeError", "too many shaders");
    Shader shader = LoadShaderFromMemory(vertex, fragment);
    if (!IsShaderValid(shader)) return spy_error(c, "ValueError", "the shader does not compile");
    shaders[shader_count] = shader;
    return spy_int(c, (int64_t)shader_count++);
}
static Shader *shader_at(SPYContext *c, SPYValue *index) {
    int64_t i;
    if (spy_as_int(c, index, &i)) return NULL;
    if (i < 0 || (size_t)i >= shader_count) { spy_error(c, "IndexError", "no such shader"); return NULL; }
    return &shaders[i];
}
/* set_uniform(shader, name, value): an int, a float, a 3-vector, or a 4x4
 * matrix (16 numbers), as the value is. */
static SPYValue *set_uniform(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, void *data) {
    (void)data;
    if (kw || argc != 3) return spy_error(c, "TypeError", "set_uniform takes a shader, a name and a value");
    Shader *shader = shader_at(c, argv[0]);
    const char *name = shader ? spy_as_string(c, argv[1], NULL) : NULL;
    if (!name) return NULL;
    int location = GetShaderLocation(*shader, name);
    SPYType type = spy_type(argv[2]);
    if (type == SPY_INT || type == SPY_BOOL) {
        int64_t i;
        if (spy_as_int(c, argv[2], &i)) return NULL;
        int value = (int)i;
        SetShaderValue(*shader, location, &value, SHADER_UNIFORM_INT);
    } else if (type == SPY_FLOAT) {
        double x;
        if (spy_as_float(c, argv[2], &x)) return NULL;
        float value = (float)x;
        SetShaderValue(*shader, location, &value, SHADER_UNIFORM_FLOAT);
    } else {
        size_t n;
        float *a = floats(c, argv[2], &n);
        if (!a) return NULL;
        if (n == 3) SetShaderValue(*shader, location, a, SHADER_UNIFORM_VEC3);
        else if (n == 16) SetShaderValueMatrix(*shader, location, to_matrix(a));
        free(a);
        if (n != 3 && n != 16) return spy_error(c, "ValueError", "a uniform vector has 3 numbers and a matrix 16");
    }
    return spy_none(c);
}

/* load_mesh(data, stride): triangles from a flat sequence of numbers, as
 * craft/cube.py writes them. Each vertex is a position, a normal and a
 * texture coordinate (stride 8), then ambient occlusion and light, which
 * the shader reads as a second texture coordinate (stride 10). */
static SPYValue *load_mesh(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, void *data) {
    (void)data; int stride;
    if (kw || argc != 2) return spy_error(c, "TypeError", "load_mesh takes the vertices and their stride");
    if (args(c, 1, argv + 1, NULL, "i", &stride)) return NULL;
    if (stride != 8 && stride != 10) return spy_error(c, "ValueError", "a vertex has 8 or 10 numbers");
    size_t n;
    float *a = floats(c, argv[0], &n);
    if (!a) return NULL;
    size_t vertices = n / (size_t)stride;
    if (n % (size_t)stride || vertices % 3 || !vertices) { free(a); return spy_error(c, "ValueError", "not a whole number of triangles"); }
    size_t slot = 0;
    while (slot < mesh_count && meshes[slot].vaoId) slot++;
    if (slot == mesh_count) {
        Mesh *more = realloc(meshes, (mesh_count + 1) * sizeof *meshes);
        if (!more) { free(a); return spy_error(c, "MemoryError", "out of memory"); }
        meshes = more;
        mesh_count++;
    }
    Mesh mesh = {0};
    mesh.vertexCount = (int)vertices;
    mesh.triangleCount = (int)(vertices / 3);
    mesh.vertices = RL_CALLOC(vertices * 3, sizeof(float));
    mesh.normals = RL_CALLOC(vertices * 3, sizeof(float));
    mesh.texcoords = RL_CALLOC(vertices * 2, sizeof(float));
    if (stride == 10) mesh.texcoords2 = RL_CALLOC(vertices * 2, sizeof(float));
    if (!mesh.vertices || !mesh.normals || !mesh.texcoords || (stride == 10 && !mesh.texcoords2)) {
        free(a); UnloadMesh(mesh);
        return spy_error(c, "MemoryError", "out of memory");
    }
    for (size_t i = 0; i < vertices; i++) {
        const float *v = a + i * (size_t)stride;
        memcpy(mesh.vertices + i * 3, v, 3 * sizeof(float));
        memcpy(mesh.normals + i * 3, v + 3, 3 * sizeof(float));
        memcpy(mesh.texcoords + i * 2, v + 6, 2 * sizeof(float));
        if (stride == 10) memcpy(mesh.texcoords2 + i * 2, v + 8, 2 * sizeof(float));
    }
    free(a);
    UploadMesh(&mesh, false);
    /* The GPU holds the vertices now; keep only the buffer handles. */
    RL_FREE(mesh.vertices); RL_FREE(mesh.normals); RL_FREE(mesh.texcoords); RL_FREE(mesh.texcoords2);
    mesh.vertices = mesh.normals = mesh.texcoords = mesh.texcoords2 = NULL;
    meshes[slot] = mesh;
    return spy_int(c, (int64_t)slot);
}
static Mesh *mesh_at(SPYContext *c, SPYValue *index) {
    int64_t i;
    if (spy_as_int(c, index, &i)) return NULL;
    if (i < 0 || (size_t)i >= mesh_count || !meshes[i].vaoId) { spy_error(c, "IndexError", "no such mesh"); return NULL; }
    return &meshes[i];
}
static SPYValue *unload_mesh(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, void *data) {
    (void)data;
    if (kw || argc != 1) return spy_error(c, "TypeError", "unload_mesh takes a mesh");
    Mesh *mesh = mesh_at(c, argv[0]);
    if (!mesh) return NULL;
    UnloadMesh(*mesh);
    *mesh = (Mesh){0};
    return spy_none(c);
}
/* draw_mesh(mesh, shader, texture0, texture1): texture1 may be -1. The
 * shader places the vertices by its own matrix uniform. */
static SPYValue *draw_mesh(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, void *data) {
    (void)data; int t0, t1;
    if (kw || argc != 4) return spy_error(c, "TypeError", "draw_mesh takes a mesh, a shader and two textures");
    Mesh *mesh = mesh_at(c, argv[0]);
    Shader *shader = mesh ? shader_at(c, argv[1]) : NULL;
    if (!shader || args(c, 2, argv + 2, NULL, "ii", &t0, &t1)) return NULL;
    if (t0 < 0 || (size_t)t0 >= texture_count || t1 < -1 || t1 >= (int)texture_count) return spy_error(c, "IndexError", "no such texture");
    MaterialMap maps[12] = {0}; /* raylib's MAX_MATERIAL_MAPS, from its config.h */
    maps[MATERIAL_MAP_DIFFUSE] = (MaterialMap){textures[t0], WHITE, 0};
    if (t1 >= 0) maps[MATERIAL_MAP_SPECULAR] = (MaterialMap){textures[t1], WHITE, 0};
    DrawMesh(*mesh, (Material){*shader, maps, {0}}, (Matrix){1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1});
    return spy_none(c);
}
/* set_depth(test, write) and set_culling(on): the GL state the game sets
 * around its passes. Drawing queued so far is flushed under the old state. */
static SPYValue *set_depth(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, void *data) {
    (void)data;
    if (kw || argc != 2) return spy_error(c, "TypeError", "set_depth takes two flags");
    rlDrawRenderBatchActive();
    if (spy_truth(argv[0])) rlEnableDepthTest(); else rlDisableDepthTest();
    if (spy_truth(argv[1])) rlEnableDepthMask(); else rlDisableDepthMask();
    return spy_none(c);
}
static SPYValue *set_culling(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, void *data) {
    (void)data;
    if (kw || argc != 1) return spy_error(c, "TypeError", "set_culling takes a flag");
    rlDrawRenderBatchActive();
    if (spy_truth(argv[0])) rlEnableBackfaceCulling(); else rlDisableBackfaceCulling();
    return spy_none(c);
}
/* draw_lines(matrix, points, color): line segments between pairs of
 * (x, y, z) points, placed by matrix. */
static SPYValue *draw_lines(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, void *data) {
    (void)data; Color color;
    if (kw || argc != 3) return spy_error(c, "TypeError", "draw_lines takes a matrix, points and a color");
    if (args(c, 1, argv + 2, NULL, "c", &color)) return NULL;
    size_t m, n;
    float *a = floats(c, argv[0], &m);
    if (!a) return NULL;
    float *p = m == 16 ? floats(c, argv[1], &n) : NULL;
    if (!p) { free(a); return spy_error_type(c)[0] ? NULL : spy_error(c, "ValueError", "a matrix has 16 numbers"); }
    if (n % 6) { free(a); free(p); return spy_error(c, "ValueError", "lines need pairs of 3-D points"); }
    rlDrawRenderBatchActive();
    Matrix projection = rlGetMatrixProjection(), modelview = rlGetMatrixModelview();
    rlSetMatrixProjection(to_matrix(a));
    rlSetMatrixModelview((Matrix){1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1});
    rlBegin(RL_LINES);
    rlColor4ub(color.r, color.g, color.b, color.a);
    for (size_t i = 0; i < n; i += 3) rlVertex3f(p[i], p[i + 1], p[i + 2]);
    rlEnd();
    rlDrawRenderBatchActive();
    rlSetMatrixProjection(projection);
    rlSetMatrixModelview(modelview);
    free(a); free(p);
    return spy_none(c);
}
/* begin_invert() and end_invert(): white drawn between them inverts the
 * colors beneath, as a GL_INVERT logic op would, so the crosshairs show on
 * any background. */
static SPYValue *begin_invert(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, void *data) {
    (void)data;
    if (args(c, argc, argv, kw, "")) return NULL;
    rlSetBlendFactors(RL_ONE_MINUS_DST_COLOR, RL_ZERO, RL_FUNC_ADD);
    BeginBlendMode(BLEND_CUSTOM);
    return spy_none(c);
}
static SPYValue *end_invert(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, void *data) {
    (void)data;
    if (args(c, argc, argv, kw, "")) return NULL;
    EndBlendMode();
    return spy_none(c);
}

static const struct { const char *name; SPYNativeKeywords fn; } functions[] = {
    {"init_window", init_window}, {"close_window", close_window},
    {"run", run}, {"get_time", get_time},
    {"get_fps", get_fps}, {"get_screen_size", get_screen_size},
    {"is_key_down", is_key_down}, {"is_key_pressed", is_key_pressed},
    {"get_char_pressed", get_char_pressed}, {"is_mouse_button_pressed", is_mouse_button_pressed},
    {"get_mouse_delta", get_mouse_delta},
    {"is_mouse_button_down", is_mouse_button_down}, {"is_mouse_button_released", is_mouse_button_released},
    {"get_touches", get_touches}, {"get_mouse_wheel_move", get_mouse_wheel_move},
    {"disable_cursor", disable_cursor}, {"enable_cursor", enable_cursor},
    {"is_cursor_hidden", is_cursor_hidden},
    {"begin_drawing", begin_drawing}, {"end_drawing", end_drawing},
    {"clear_background", clear_background}, {"draw_rectangle", draw_rectangle},
    {"draw_circle", draw_circle},
    {"draw_text", draw_text}, {"measure_text", measure_text},
    {"load_texture", load_texture}, {"load_shader", load_shader}, {"set_uniform", set_uniform},
    {"load_mesh", load_mesh}, {"unload_mesh", unload_mesh}, {"draw_mesh", draw_mesh},
    {"set_depth", set_depth}, {"set_culling", set_culling}, {"draw_lines", draw_lines},
    {"begin_invert", begin_invert}, {"end_invert", end_invert},
};
static const struct { const char *name; int value; } constants[] = {
    {"KEY_A", KEY_A}, {"KEY_D", KEY_D}, {"KEY_E", KEY_E}, {"KEY_F", KEY_F},
    {"KEY_R", KEY_R}, {"KEY_S", KEY_S}, {"KEY_V", KEY_V}, {"KEY_W", KEY_W},
    {"KEY_ZERO", KEY_ZERO}, {"KEY_ONE", KEY_ONE}, {"KEY_NINE", KEY_NINE},
    {"KEY_SPACE", KEY_SPACE}, {"KEY_TAB", KEY_TAB}, {"KEY_ENTER", KEY_ENTER},
    {"KEY_BACKSPACE", KEY_BACKSPACE}, {"KEY_ESCAPE", KEY_ESCAPE},
    {"KEY_LEFT", KEY_LEFT}, {"KEY_RIGHT", KEY_RIGHT}, {"KEY_UP", KEY_UP}, {"KEY_DOWN", KEY_DOWN},
    {"KEY_LEFT_SHIFT", KEY_LEFT_SHIFT}, {"KEY_RIGHT_SHIFT", KEY_RIGHT_SHIFT},
    {"KEY_LEFT_CONTROL", KEY_LEFT_CONTROL}, {"KEY_RIGHT_CONTROL", KEY_RIGHT_CONTROL},
    {"KEY_LEFT_SUPER", KEY_LEFT_SUPER}, {"KEY_RIGHT_SUPER", KEY_RIGHT_SUPER},
    {"MOUSE_BUTTON_LEFT", MOUSE_BUTTON_LEFT}, {"MOUSE_BUTTON_RIGHT", MOUSE_BUTTON_RIGHT},
    {"MOUSE_BUTTON_MIDDLE", MOUSE_BUTTON_MIDDLE},
};

static int set_owned(SPYContext *c, SPYValue *module, const char *name, SPYValue *v) {
    int status = !v || spy_set_attr(c, module, name, v);
    spy_release(v);
    return status ? -1 : 0;
}
/* What a shader's source starts with: GLSL 3.30 for desktop OpenGL, or
 * GLSL ES 3.00 for WebGL 2, whose stages must agree on precision. */
#ifdef __EMSCRIPTEN__
static const char glsl_header[] = "#version 300 es\nprecision highp float;\nprecision highp int;\n";
#else
static const char glsl_header[] = "#version 330\n";
#endif

static int raylib_init(SPYContext *c, SPYValue *module) {
    if (set_owned(c, module, "GLSL_HEADER", spy_string(c, glsl_header, strlen(glsl_header)))) return -1;
    for (size_t i = 0; i < sizeof(functions) / sizeof(*functions); i++)
        if (set_owned(c, module, functions[i].name, spy_native(c, functions[i].name, functions[i].fn, NULL, NULL))) return -1;
    for (size_t i = 0; i < sizeof(constants) / sizeof(*constants); i++)
        if (set_owned(c, module, constants[i].name, spy_int(c, constants[i].value))) return -1;
    return 0;
}

/* noise: simplex2(x, y, octaves, persistence, lacunarity) and simplex3(x,
 * y, z, ...), fractal simplex noise from noise.c. */
static SPYValue *simplex2_(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, void *data) {
    (void)data; double x, y, persistence, lacunarity; int octaves;
    if (args(c, argc, argv, kw, "nninn", &x, &y, &octaves, &persistence, &lacunarity)) return NULL;
    return spy_float(c, simplex2((float)x, (float)y, octaves, (float)persistence, (float)lacunarity));
}
static SPYValue *simplex3_(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, void *data) {
    (void)data; double x, y, z, persistence, lacunarity; int octaves;
    if (args(c, argc, argv, kw, "nnninn", &x, &y, &z, &octaves, &persistence, &lacunarity)) return NULL;
    return spy_float(c, simplex3((float)x, (float)y, (float)z, octaves, (float)persistence, (float)lacunarity));
}
static int noise_init(SPYContext *c, SPYValue *module) {
    return set_owned(c, module, "simplex2", spy_native(c, "simplex2", simplex2_, NULL, NULL))
        || set_owned(c, module, "simplex3", spy_native(c, "simplex3", simplex3_, NULL, NULL)) ? -1 : 0;
}

/* libm: sin, cos, tan, acos and atan2 in radians. */
static const struct unary { const char *name; double (*f)(double); } unary[] = {
    {"sin", sin}, {"cos", cos}, {"tan", tan}, {"acos", acos},
};
static SPYValue *call_unary(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, void *data) {
    double x;
    return args(c, argc, argv, kw, "n", &x) ? NULL : spy_float(c, ((const struct unary *)data)->f(x));
}
static SPYValue *atan2_(SPYContext *c, size_t argc, SPYValue *const *argv, SPYValue *kw, void *data) {
    (void)data; double y, x;
    return args(c, argc, argv, kw, "nn", &y, &x) ? NULL : spy_float(c, atan2(y, x));
}
static int libm_init(SPYContext *c, SPYValue *module) {
    for (size_t i = 0; i < sizeof(unary) / sizeof(*unary); i++)
        if (set_owned(c, module, unary[i].name, spy_native(c, unary[i].name, call_unary, (void *)&unary[i], NULL))) return -1;
    return set_owned(c, module, "atan2", spy_native(c, "atan2", atan2_, NULL, NULL));
}

/* The bundle spyc -c -N smallcraft writes: the entry's source and a loader
 * for every module it imports. */
extern const char spy_smallcraft[];
char *smallcraft_load(void *, const char *);

int main(void) {
    SPYContext *c = spy_context_new();
    if (!c) { fputs("cannot start\n", stderr); return 1; }
    spy_set_output(c, host_output, stdout);
    spy_set_flush(c, host_flush);
    spy_set_module_loader(c, smallcraft_load, NULL);
    /* Without the mount (a read-only directory, say) the game plays unsaved. */
    spy_mount(c, ".", NULL, 0);
    int status = spy_new_module(c, "raylib", raylib_init) || spy_new_module(c, "noise", noise_init)
        || spy_new_module(c, "libm", libm_init) || spy_exec(c, spy_smallcraft, "smallcraft.py") ? host_exit_status(c) : 0;
#ifdef __EMSCRIPTEN__
    /* The browser goes on calling the frames: keep the context. */
    if (!status) return 0;
#endif
    if (IsWindowReady()) CloseWindow();
    spy_context_free(c);
    return status < 0 ? 1 : status;
}
