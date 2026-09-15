--[[
Aneis do widget da area de trabalho, na versao "aneis" do d3bian-init-bigsur.

Adaptado do MX-CoreBlue (MX Linux, mx-conky-data), que parte do Clock Rings de
londonali1010, reeditado por despot77 e Altin, e foi usado no setup Xfce Big
Sur do lsteam. Mudancas: carrega o cairo_xlib do conky novo, libera a
superficie a cada quadro, segue a cor de destaque e descobre a interface de
rede pela rota padrao, em vez de eth0 e wlan0.
]]

require 'cairo'
-- desde o conky 1.11 a ponte com o X fica num modulo separado
pcall(require, 'cairo_xlib')

local COR = 0x@@widget_cor@@

-- x e y contam do canto superior esquerdo da janela do conky
local aneis = {
    -- relogio: horas, minutos, segundos, dia e mes
    {nome='time', arg='%I.%M', max=12, fundo=0.15, frente=0.30, x=100, y=168, raio=50, inicio=0, fim=360},
    {nome='time', arg='%M.%S', max=60, fundo=0.10, frente=0.40, x=100, y=168, raio=66, inicio=0, fim=360},
    {nome='time', arg='%S',    max=60, fundo=0.10, frente=0.60, x=100, y=168, raio=72, inicio=0, fim=360},
    {nome='time', arg='%d',    max=31, fundo=0.10, frente=0.80, x=100, y=168, raio=80, inicio=-90, fim=90},
    {nome='time', arg='%m',    max=12, fundo=0.10, frente=1.00, x=100, y=168, raio=86, inicio=-90, fim=90},
    {nome='bateria', arg='',   max=100, fundo=0.20, frente=0.80, x=232, y=110, raio=27, inicio=-90, fim=270},
    -- processador, um anel por nucleo (os dois primeiros)
    {nome='cpu', arg='cpu1',   max=100, fundo=0.30, frente=0.80, x=165, y=320, raio=25, inicio=-90, fim=180},
    {nome='cpu', arg='cpu2',   max=100, fundo=0.30, frente=0.80, x=240, y=320, raio=25, inicio=-90, fim=180},
    -- disco, memoria e troca
    {nome='fs_used_perc', arg='/', max=100, fundo=0.20, frente=0.80, x=40,  y=525, raio=25, inicio=-90, fim=180},
    {nome='memperc', arg='',   max=100, fundo=0.20, frente=0.80, x=140, y=525, raio=25, inicio=-90, fim=180},
    {nome='swapperc', arg='',  max=100, fundo=0.20, frente=0.80, x=240, y=525, raio=25, inicio=-90, fim=180},
}

local RELOGIO = {x=100, y=168, raio=65}

local function rgba(cor, alfa)
    return ((cor / 0x10000) % 0x100) / 255, ((cor / 0x100) % 0x100) / 255, (cor % 0x100) / 255, alfa
end

local function anel(cr, fracao, a)
    local espessura = 5
    local ang0 = a.inicio * (2 * math.pi / 360) - math.pi / 2
    local angf = a.fim * (2 * math.pi / 360) - math.pi / 2
    fracao = math.max(0, math.min(1, fracao))

    cairo_set_line_width(cr, espessura)
    cairo_arc(cr, a.x, a.y, a.raio, ang0, angf)
    cairo_set_source_rgba(cr, rgba(0xffffff, a.fundo))
    cairo_stroke(cr)

    cairo_arc(cr, a.x, a.y, a.raio, ang0, ang0 + fracao * (angf - ang0))
    cairo_set_source_rgba(cr, rgba(COR, a.frente))
    cairo_stroke(cr)
end

local function valor(a)
    if a.nome == 'time' then
        if a.arg == '%I.%M' then
            return math.fmod(tonumber(os.date('%I')), 12) + tonumber(os.date('%M')) / 60
        elseif a.arg == '%M.%S' then
            return tonumber(os.date('%M')) + tonumber(os.date('%S')) / 60
        end
        return tonumber(os.date(a.arg))
    elseif a.nome == 'bateria' then
        return tonumber(conky_parse('${if_existing /sys/class/power_supply/BAT0}${battery_percent BAT0}'
            .. '${else}${if_existing /sys/class/power_supply/BAT1}${battery_percent BAT1}${else}0${endif}${endif}'))
    end
    return tonumber(conky_parse(string.format('${%s %s}', a.nome, a.arg)))
end

local function ponteiros(cr)
    local s = tonumber(os.date('%S'))
    local m = tonumber(os.date('%M'))
    local h = tonumber(os.date('%I'))
    local arco_s = (2 * math.pi / 60) * s
    local arco_m = (2 * math.pi / 60) * m + arco_s / 60
    local arco_h = (2 * math.pi / 12) * h + arco_m / 12
    local xc, yc, r = RELOGIO.x, RELOGIO.y, RELOGIO.raio

    cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND)
    cairo_set_source_rgba(cr, 1, 1, 1, 1)
    for _, p in ipairs({{arco_h, 0.74, 5}, {arco_m, 1.0, 3}, {arco_s, 1.05, 1}}) do
        cairo_move_to(cr, xc, yc)
        cairo_line_to(cr, xc + p[2] * r * math.sin(p[1]), yc - p[2] * r * math.cos(p[1]))
        cairo_set_line_width(cr, p[3])
        cairo_stroke(cr)
    end
end

function conky_aneis()
    if conky_window == nil then return end
    local superficie = cairo_xlib_surface_create(conky_window.display, conky_window.drawable,
        conky_window.visual, conky_window.width, conky_window.height)
    local cr = cairo_create(superficie)

    -- o 'cpu' devolve lixo nas primeiras leituras, entao os aneis esperam
    if tonumber(conky_parse('${updates}')) > 3 then
        for _, a in ipairs(aneis) do
            local v = valor(a)
            if v then anel(cr, v / a.max, a) end
        end
    end
    ponteiros(cr)

    cairo_destroy(cr)
    cairo_surface_destroy(superficie)
end

-- interface da rota padrao, lida a cada chamada: o notebook troca de rede
local function interface()
    local f = io.open('/proc/net/route')
    if not f then return nil end
    for linha in f:lines() do
        local nome, destino = linha:match('^(%S+)%s+(%x+)')
        if destino == '00000000' then f:close() return nome end
    end
    f:close()
    return nil
end

function conky_rede()
    local i = interface()
    if not i then
        return '${color1}Rede:$color${alignr}sem conexão'
    end
    return table.concat({
        '${color1}Rede:$color${alignr}' .. i,
        '${color1}Endereço:$color${alignr}${addr ' .. i .. '}',
        '${color1}Baixando:$color ${downspeed ' .. i .. '}${alignr}${color1}Enviando:$color ${upspeed ' .. i .. '}',
        '${color1}Total:$color ${totaldown ' .. i .. '}${alignr}${color1}Total:$color ${totalup ' .. i .. '}',
    }, '\n')
end

local sistema_nome
function conky_sistema()
    if not sistema_nome then
        sistema_nome = 'Linux'
        local f = io.open('/etc/os-release')
        if f then
            for linha in f:lines() do
                local v = linha:match('^PRETTY_NAME="?([^"]*)"?')
                if v then sistema_nome = v break end
            end
            f:close()
        end
    end
    return sistema_nome
end
