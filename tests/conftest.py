"""启用 HA 自定义组件测试框架,并让 custom_components 在收集期可导入。"""
import sys

sys.path.insert(0, "/config/")  # 使 custom_components.leelen_home 可在测试模块 import

pytest_plugins = "pytest_homeassistant_custom_component"
