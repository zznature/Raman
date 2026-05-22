LabSpec 6.5.1 安装包里自带了这份文档，入口是：

C:/HORIBA/LabSpec_6_5_1/HELP/VBS/menu.html

它不是单独的 PDF，而是一组 HTML API 页面，目录在：

C:\HORIBA\LabSpec_6_5_1\HELP\VBS\

里面包含 Acq、MoveMotor、GetValue、MapEx、Video、Treat 等函数说明和示例。明确标为 AutoActiveX 的页面包括：

ConvertUnit.html、GetMappingParams.html、GetValueEx.html、GetValueSimple.html、LoadConfig.html、MapEx.html、Print.html、SaveConfig.html、
SetDetectorZone.html、Template.html、TickCount.html

ActiveX 控件文件也在安装包内：

C:\HORIBA\LabSpec_6_5_1\REG64\COMMON\NFActiveX.ocx
C:\HORIBA\LabSpec_6_5_1\Register\Common\NFActiveX.ocx

对应注册脚本：

C:\HORIBA\LabSpec_6_5_1\register64.bat
C:\HORIBA\LabSpec_6_5_1\register.bat

公开网页方面，HORIBA 官方页面确认 LabSpec 6 支持 VBS 和 ActiveX，并说明 ActiveX 用于让第三方软件远程控制 LabSpec 6 的硬件控制、数据采集和数据处理功能：
https://www.horiba.com/usa/scientific/products/detail/action/show/Product/script-and-activex-1658/
中文页：
https://www.horiba.com/chn/scientific/products/detail-1/action/show/Product/script-and-activex-1658/

另一个官方技术说明 PDF 也提到 ActiveX 和“full documentation on specific LabSpec 6 ActiveX components”：
https://www.horiba.com/fileadmin/uploads/Scientific/Documents/Raman/SO-TN04_Customization_and_Automation_with_LabSpec_6.pdf