## Importando bibliotecas
import pvlib
import windpowerlib
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

# PRODUÇÃO DE ENERGIA
# latitude, longitude, name, altitude, timezone
coordinates = [
    (-3.57168, -38.84797, 'ZPE Pecém', 26, 'Etc/GMT-3'),
]

# LEITURA DE ESPECIFICAÇÕES DE EQUIPAMENTOS FOTOVOLTAICOS DE ARQUIVOS CSV
# Lendo especificações do inversor e do módulo a partir dos arquivos CSV
inverter_data = pd.read_csv('CEC Inverters.csv', index_col=0)
module_data = pd.read_csv('CEC Modules.csv', index_col=0)

# Selecionando o inversor e o módulo específicos
inverter = inverter_data.loc['CSI Solar Co - Ltd : CSI-125K-T600GL02-U [600V]']
module = module_data.loc['Chint New Energy Technology Co. Ltd. CHSM72M(DG)/F-BH-550']

# Configuração do sistema
modules_per_string = 35
inverters = 10
strings_per_inverter = 10
system = {'module': module, 'inverter': inverter, 'surface_azimuth': 180, 'surface_tilt': coordinates[0][0]}

# Baixa os dados climáticos TMY para cada localização
tmys = []
for location in coordinates:
    latitude, longitude, name, altitude, timezone = location
    weather = pvlib.iotools.get_pvgis_tmy(latitude, longitude)[0]
    weather.index.name = "utc_time"
    tmys.append(weather)

energies = {}
for location, weather in zip(coordinates, tmys):
    latitude, longitude, name, altitude, timezone = location
    system['surface_tilt'] = latitude
    solpos = pvlib.solarposition.get_solarposition(
        time=weather.index,
        latitude=latitude,
        longitude=longitude,
        altitude=altitude,
        temperature=weather["temp_air"],
        pressure=pvlib.atmosphere.alt2pres(altitude),
    )
    dni_extra = pvlib.irradiance.get_extra_radiation(weather.index)
    airmass = pvlib.atmosphere.get_relative_airmass(solpos['apparent_zenith'])
    pressure = pvlib.atmosphere.alt2pres(altitude)
    am_abs = pvlib.atmosphere.get_absolute_airmass(airmass, pressure)
    aoi = pvlib.irradiance.aoi(
        system['surface_tilt'],
        system['surface_azimuth'],
        solpos["apparent_zenith"],
        solpos["azimuth"],
    )
    total_irradiance = pvlib.irradiance.get_total_irradiance(
        system['surface_tilt'],
        system['surface_azimuth'],
        solpos['apparent_zenith'],
        solpos['azimuth'],
        weather['dni'],
        weather['ghi'],
        weather['dhi'],
        dni_extra=dni_extra,
        model='haydavies',
    )
    # Cálculo da temperatura da célula com o modelo NOCT
    cell_temperature = pvlib.temperature.pvsyst_cell(
        poa_global=total_irradiance['poa_global'],
        temp_air=weather["temp_air"],
        wind_speed=weather["wind_speed"],
        u_c=29,  # Eficiência média do módulo (pode ser ajustada conforme necessário)
        u_v=0  # Absorptância do módulo (ajustável conforme o tipo de módulo)
    )

    gamma_pdc = module.get('gamma_pdc', -0.0034)

    # Cálculo da irradiância efetiva para o modelo CEC
    effective_irradiance = total_irradiance['poa_global']
    dc = pvlib.pvsystem.pvwatts_dc(effective_irradiance, cell_temperature, module['STC'], gamma_pdc=gamma_pdc)

    # Multiplicar a potência DC pela quantidade de módulos e strings
    dc *= modules_per_string * strings_per_inverter
    pac0_value = float(inverter['Paco'])

    # Cálculo da saída de potência CA usando o modelo CEC para o inversor
    ac = pvlib.inverter.pvwatts(pdc=dc, pdc0=pac0_value, eta_inv_nom=0.96, eta_inv_ref=0.9637)
    ac *= inverters

    annual_energy = ac.sum()
    energies[name] = annual_energy

energies = pd.Series(energies)

# based on the parameters specified above, these are in W*hrs
print(energies)

energies.plot(kind='bar', rot=0)
plt.ylabel('Yearly energy yield (W hr)')
plt.show()
