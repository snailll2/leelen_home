import socket
import threading
import time
from enum import Enum
from typing import Optional, Callable

from .entity.GatewayInfo import GatewayInfo
from .utils.LogUtils import LogUtils
from .utils.SslUtils import SslUtils
from .common.DefaultThreadPool import DefaultThreadPool



class ConnectState(Enum):
    NONE = ("None", 0)
    CONNECTING = ("Connecting", 1)
    CONNECTED = ("Connected", 2)

    def __init__(self, description, code):
        self.description = description
        self.code = code


class LogonState(Enum):
    NONE = ("None", 0)
    LOGGING_ON = ("LoggingOn", 1)
    LOGGED_ON = ("LoggedOn", 2)

    def __init__(self, description, code):
        self.description = description
        self.code = code


class BaseConnect:
    MAX_CONNECTING_COUNT = 5
    MSG_TYPE_CONNECT_RESULT = 0
    MSG_TYPE_SERVER_HOST_EMPTY = 1

    def __init__(self, server_host: str, server_port: int, username: str, password: str):
        self.server_host = server_host
        self.server_port = server_port
        self.username = username
        self.password = password
        self.socket_lock = threading.Lock()
        self.recv_lock = threading.Lock()
        self.send_lock = threading.Lock()

        self.m_connect_state = ConnectState.NONE
        self.m_logon_state = LogonState.NONE
        self.m_recv_data_running = False
        self.m_socket: Optional[socket.socket] = None
        self.m_output_stream: Optional[socket.SocketIO] = None
        self.m_connecting_count = 0
        self.heartbeat_data = self.create_heartbeat_data()
        self.heartbeat_interval = 5  # seconds
        self.pre_heartbeat_recv = False
        self.pre_heartbeat_recv_time = -1
        self.pre_heartbeat_start_time = time.time()
        self.pre_heartbeat_send_time = -1
        self.connect_retry_count = 0
        self.show_log = True
        self.tag = "🍺 BaseConnect:"

        # Thread pool for async operations
        # self.thread_pool = DefaultThreadPool.get_instance()
        self.scheduled_executor: Optional[threading.Timer] = None
        # self.heartbeat_executor: Optional[threading.Timer] = None
        self.connect_executor: Optional[threading.Timer] = None
        self.recv_data_executor: Optional[threading.Timer] = None

        # Initialize runnables
        self.r_heartbeat = self._heartbeat_runnable()
        self.r_connect = self._connect_runnable()
        self.r_recv_data = self._recv_data_runnable()

    def _heartbeat_runnable(self) -> Callable:
        def run():
            # if self.show_log:
                # LogUtils.d(self.tag,f"Heartbeat data: {self.heartbeat_data.hex()}")
            self.send_heartbeat(self.heartbeat_data)

        return run

    def _connect_runnable(self) -> Callable:
        def run():
            if not hasattr(run, 'running'):
                run.running = False

            if run.running:
                return

            run.running = True
            self.set_connect_state(ConnectState.CONNECTING)
            self.connect_retry_count += 1

            if not self.server_host:
                if self.show_log:
                    LogUtils.w(self.tag,f"Server host is empty")
                    return
                # self.conn_handler.send_empty_message(self.MSG_TYPE_SERVER_HOST_EMPTY)
            else:
                try:
                    # Close existing socket if any
                    if self.m_socket:
                        self.m_socket.close()
                        self.m_socket = None

                    context = SslUtils.get_lan_socket_ssl_context(
                        "308209C10201033082098706092A864886F70D010701A082097804820974308209703082042706092A864886F70D010706A0820418308204140201003082040D06092A864886F70D010701301C060A2A864886F70D010C0106300E0408899CEC34E7D92C7302020800808203E08B8963EB60BF84222920C89FBF6E726C47733C103248CF780699579B7091341A3290F69348AB069A20C6D21DC3D104148F77AEFF58155BCC7C778178FED8E42260941D561C59221A7E59579EBA5D6A401FF016586A99984732BE153E6D6C48659C07550B98EFB336A7FB5081FD172E1D9A36E15818667E5BD07ED21B530C4AD77255E300938ACF73B2C492A0A55E6DB72DC10CDD3A75F011BDDEB722D761C251760804F8E3293B7488813E7B494BE49284B0A2BCF30BB926EC013C4A7ED239F1C6747F24CA5C68BC49EE08BE08BB31801512480A1E881F03D1A8394D1FBDAFB7C1AB29E256F667F92FEFEA85F8CBD7D09D6BFB20B7F4AAA314681D91907C926A89B863DA4626DBD5EABE68DB66A987B21CF0ADD488EED228B2401BE18FEFDA14892712C98B38EF8AC7974E7AF3874A1F8F128881329A558CE13E1F3798AC979EBFBE72E2D5DFC7B58A944F72B2612BBC92174ECAF68E405A9E281DE7E9B5A4BB4E45D8C9C7DE79AB0FA440A12D1B9A7692F86B18849D87E851DAD79CAAAD5019A53D711A0E6E312D4FEBCFA610B470E9AE7B7F394354D0423930023FFDA9EA6663E967AF38EEF126115AA60D479E1B989C9B4A01891A2FFCA1F32CEBD4E7BA26F33DC5209D83B6D418CA1A8C2A4EFC4A6079BDE966C565F4ABD2E86F9160B4F52228675DD9550D73523E5FA32E94EF28A834568113134F24D776651AA5C899F5D97FFFEAD113075716DB4444221B85B57583E1380ACABD47E368A70B0E906187E2D19C6F23F7287940D8DDECEA6DA8673DB6CC018DD8ED669F7A2B18FC5676E88404F9B2E4E6A40293A5CDCFF60DCE6B76AD9C4942068DE2073D08975D3808B2BE00F2E7E4B852E589D63FF51EAC21B23168BFA6FA9FB02C119BA36435ABFB34400827EF9B638285FB735B2F256B5A6EAC55F5A00013141D997A15FF66AD9405E2296F0A8F56E8A02DC22F4C49A28194578F949BE848F6B986BB123A153FEF16B9C33CE2918B2365DE379948E269AF4C10346C9F60801F80481C57D76C8506B0D35A516E5DBF39CB7B4EB880BC971AF3887716415AAA99E9F91B7C47D969E6CB1A530E45A00B4AACCDA7E9338AD8BBF982D49FCE04B65F07FD5F5682966D4051DB3884EF3645750BA09432F368D795013FD53527DF5099385F66B3C2C6DFA9B76248004BB8588F5903987408AB0F5850E27EB2076CF1DEDFEB507A37036B645AC0429F1205CD6E5FBE2F4C11591F5593B5113EE9E734BCBAD437EE41AB0C342014FBAD6FFF8E4C23C459FF2B9BDAC1ECDFB7BCBA94D59B40836B78B31275256D193DFF82217C013D9040470E1BF14197344BAE066969F9BF712C7B8014E577043CED0AE8132A8F4A22B5B2269A0B3EDBD8197620330511B3445CFE75F0EE786B3082054106092A864886F70D010701A08205320482052E3082052A30820526060B2A864886F70D010C0A0102A08204EE308204EA301C060A2A864886F70D010C0103300E04089E75AC9CC743260402020800048204C861E584702277719AE46DC020D632F0F1C896312E524805D52A2A32A8E70869B2AEDCB426C1958F227449318DF381489E418D82F1DC145FCC013BF2CA27EF3F5280F8AFCCD475A9EC910E16C70EB2BF74DFDDB73FFA8875D2324095E6FA068180E38A5EFB8257E90054DDE54C46E97AA08E927C44F970B46320068E5CBDE63FAF342F7BAC9876D226D5998CE72577444642BC8ED4999F5DE5C5416A067F4D2C7081A9AF8AD9177440623A9A0911841188F4D93C6544921A27ED53028CDE6C37B8E63727B96AE0DCD05B45BFEC872F8F78063DDB99531BBF3456C1ACC356BFD155CC36FE8E1CF9B0E83F9D4F6FCD22EEC0C1C7A8E6B3A3865F3CE45C50E1E1DB7979B27EB94A71BCB7524F5CBE22B7874CAF918168132A21B1118B946BE431B216AFD7730DA6631C8BAAAF8CA11A0408B79EEE019D1688B8504EE96DD18A8C68FE1E879E76D80746AFB3A9599A197FF5A0BB43B16B145D407092D6605E7EA2B37A865FB6C965FBF9150BEABBCCA348D636D5291577FAFC70A614F815063094321883AE28D0879F7AA8DDA4442C459FC056DE82BABAB8B7F9D240F7DF086428418945D6DE31F61702D4823C1EC94D26B767861B4232837287A292A51D71DF49A47D7E9C2ECBE479D25E51AE9018808C76079D730481FBEF0819CCA21EB0A4B872C6DC3405D7BEEEC597FC82B36E92A769F9F75473A4FF5667B46A9A22893F4EB16581F9FEB3D339A85EB44322CF160C5F0D3539FC4F54697B089B22567739F481A1F5A62068242929034DFE1B1DA49112709980986EC71FF15661022BFD99750927A2074E3988FF0D335E91DD24DF9B8E4E96B05F03094457A94D088C736ECF043DB9F62E022E45C9F93618D23728977D1D5E86E68C09EFFE3D99AFD9FE37366D39DB076DF11D58A9B65650D5BA669DD992B7F8AA909C64387C79F5DBEF42B921CE13A1DE2A079062A3D506B0AA865C5261618D0ED5A7D65DD540AAB6FD6095A85B0C8DA683D56D0C54AC67A041C5F760263332E9CD41EE7AE9A513EEEA1AA8BCF57F34ED42B77354BCF3303CA739218609438B10641DA42C0661660C0EDE4CD0D6275F61E1EFE3158FA9A1AFF71925B9E68BEE5803F00B1DEC44024EC37806DAA890865164155CFFC606B5BD565871146AEA4D7DC41E7DCD259214C012F08E567A43BE30399D299050D0B10278F9DFB25EADF4E548BCBF1DE6F803A27F2E707F9B486315760ED1FE60EC1DF959B33D4870B281D87337D0E85CEAADB41356EC5BE76539F38713B426392B4370EFD654A7D2602F5692282A8086884E97FE1F8D9CF3EC490875D9CC80E35358336C3F32E2E8FEE320D487AA203A22A58776928B720F3B7E50B109C2A9DF9AE6892F4AEF95E4B86BC565D5FE588D13287D271BDCB2AC0F8CDBE142E1D87B21572E59D0BFDC6B81DFDB81F72568ADD8899EBA6DF103616B04E27481B92D988B61283254CD6CDA543F41B49A1AD52BD29BF32DCBFC2D089B6FC360481AABC385D4D820FDED48EB60F1A81B8F8E98A6FED658FFCBE77781416E2CF7169D52F52C53E3678C6C52BBE118DA1C59266C94F797D50A8BF16FBBF69AAA84902C3F187811A49E8758623E4FE783358ACBC2D9BD5D935B69FA30C538381B8AC1045E3C0409130399063C328F6E835A8CA99016EEE82E8EEC7532A1899FDDE82886CD11AAA3276C3CFB63465FEFC5D72CA2BF4F47F9DCDD786EE8CE2CC954CAC47725503125302306092A864886F70D01091531160414F40779E8F44B058423D0283CCC8E9CEA1E5B208130313021300906052B0E03021A050004146C7193E266882FF46FE9B9B5A4ACFC4372F3777B04087E4A304F61F85CBD02020800",
                        "IOTAndroidKey#$%^&%TGB",
                        # 原始 bks
                        # "0000000100000014443EEDA2B90C21B34AD4D83E92F99B45EAD9905C0000075C01000B636F646570726F6A6563740000015B12A69BF9000000000005582E353039000003DF308203DB308202C3A0030201020209009BE2E5C252C30351300D06092A864886F70D01010B0500308182310B300906035504061302636E310F300D06035504080C0666756A69616E310F300D06035504070C067869616D656E31293027060355040A0C205869616D656E204C65656C656E20546563686E6F6C6F677920434F2E2C4C5444310C300A060355040B0C03494F543118301606035504030C0F494F544C65656C656E4341726F6F743020170D3137303332373037323233315A180F32313137303330333037323233315A308182310B300906035504061302636E310F300D06035504080C0666756A69616E310F300D06035504070C067869616D656E31293027060355040A0C205869616D656E204C65656C656E20546563686E6F6C6F677920434F2E2C4C5444310C300A060355040B0C03494F543118301606035504030C0F494F544C65656C656E4341726F6F7430820122300D06092A864886F70D01010105000382010F003082010A0282010100B592EBE5B1576A0CDC34B715DF8286FF9B8524B96389F9A939D28DECD4B6E6112698EEEF9E9A4163472A9F4076FEB6A3F734D24A13CF621184C52D9FA583770B6862A21683062DDCB169564DA5D0413BF14623BA3AC1F1BAEBBA061883EB041766F0FEF5875DBA9AF4EE16EE37A86B5D800FC73F0C1E8BE076B1DEAB241C0A199B2BB6CB3E44652E48E5C0A035067FBBFF3A404182CAAAC040F2068425EF8ECBD5D7C86F11C060764705E90EC37A766B05B0EDDB67CAC1F75358A538755D58DA603095E7A984B1215C9A852E9D766EE3602F6603E303E1541BF7D6CE34E9ED269AF467959D29A72FDEC30999417C5337653EA630D5501D32C5FA4547560EA06B0203010001A350304E301D0603551D0E04160414EF717509B6C8B52B959635A1E9291BE3507D9996301F0603551D23041830168014EF717509B6C8B52B959635A1E9291BE3507D9996300C0603551D13040530030101FF300D06092A864886F70D01010B0500038201010090486039C3657242CBEB963F326909F7BB27794A202BBB8D4E3A8DFE9BBB9718ACAEBE91B822564C354F9B0107C388D83F60376CD522230C883146A3C533CCBC5EDBBC7E42B34CED172DB9BE237686FCA894AAAE5F189D593128ECC40034960FF0DEC9FC59687D422839CDDFBAE0AE7B8D91C1AA5B832AB53AE5AA9E7C271D968DE98DB1DDCF8255B4650E3FFEC427A8C554FF26DF55EFF4D255D5CB297DC59B209B8B79951F91762CBB7BD34291EB997E41658AE7552E21FE51DB5890857447929024C344D914610F2EDFB45D00E4E4D81B3D4A06ED6026C4DB76375BE26C798942C7CC42073544D47D41633B5E20CDC60F811D5E4C1A4A5DA157305508D30C0086888F58060F79FE4F9C89E35957F91E7A1E050D",
                        # "FEEDFEED000000020000000100000002000B636F646570726F6A6563740000019606C966960005582E353039000003DF308203DB308202C3A0030201020209009BE2E5C252C30351300D06092A864886F70D01010B0500308182310B300906035504061302636E310F300D06035504080C0666756A69616E310F300D06035504070C067869616D656E31293027060355040A0C205869616D656E204C65656C656E20546563686E6F6C6F677920434F2E2C4C5444310C300A060355040B0C03494F543118301606035504030C0F494F544C65656C656E4341726F6F743020170D3137303332373037323233315A180F32313137303330333037323233315A308182310B300906035504061302636E310F300D06035504080C0666756A69616E310F300D06035504070C067869616D656E31293027060355040A0C205869616D656E204C65656C656E20546563686E6F6C6F677920434F2E2C4C5444310C300A060355040B0C03494F543118301606035504030C0F494F544C65656C656E4341726F6F7430820122300D06092A864886F70D01010105000382010F003082010A0282010100B592EBE5B1576A0CDC34B715DF8286FF9B8524B96389F9A939D28DECD4B6E6112698EEEF9E9A4163472A9F4076FEB6A3F734D24A13CF621184C52D9FA583770B6862A21683062DDCB169564DA5D0413BF14623BA3AC1F1BAEBBA061883EB041766F0FEF5875DBA9AF4EE16EE37A86B5D800FC73F0C1E8BE076B1DEAB241C0A199B2BB6CB3E44652E48E5C0A035067FBBFF3A404182CAAAC040F2068425EF8ECBD5D7C86F11C060764705E90EC37A766B05B0EDDB67CAC1F75358A538755D58DA603095E7A984B1215C9A852E9D766EE3602F6603E303E1541BF7D6CE34E9ED269AF467959D29A72FDEC30999417C5337653EA630D5501D32C5FA4547560EA06B0203010001A350304E301D0603551D0E04160414EF717509B6C8B52B959635A1E9291BE3507D9996301F0603551D23041830168014EF717509B6C8B52B959635A1E9291BE3507D9996300C0603551D13040530030101FF300D06092A864886F70D01010B0500038201010090486039C3657242CBEB963F326909F7BB27794A202BBB8D4E3A8DFE9BBB9718ACAEBE91B822564C354F9B0107C388D83F60376CD522230C883146A3C533CCBC5EDBBC7E42B34CED172DB9BE237686FCA894AAAE5F189D593128ECC40034960FF0DEC9FC59687D422839CDDFBAE0AE7B8D91C1AA5B832AB53AE5AA9E7C271D968DE98DB1DDCF8255B4650E3FFEC427A8C554FF26DF55EFF4D255D5CB297DC59B209B8B79951F91762CBB7BD34291EB997E41658AE7552E21FE51DB5890857447929024C344D914610F2EDFB45D00E4E4D81B3D4A06ED6026C4DB76375BE26C798942C7CC42073544D47D41633B5E20CDC60F811D5E4C1A4A5DA157305508D30C546C390A42A883794C23AA1A160CBC72B91E2909",
                        # 转换的 p12
                        "308205620201033082050c06092a864886f70d010701a08204fd048204f9308204f5308204f106092a864886f70d010706a08204e2308204de020100308204d706092a864886f70d010701306606092a864886f70d01050d3059303806092a864886f70d01050c302b04141c10e9eb1047a22fecb494492d19f1d81948bf9402022710020120300c06082a864886f70d02090500301d060960864801650304012a0410df289aa16cb70f96ef05b821f109d2a9808204607338026b82e7384fb488f317bd8a848572f02c2eccfba465e0161f89a41dfe1f97ae6c5be2c28ce835bdcdce1de3877bec85585a80cee1bacedaf1f83296acda64bf95fc0d2e4fdca46661eaf8ba54ad92cc88ff8db487ceddbbb93175cda5c5997123f00db02373f16c8000287f1f386fdf27daff551779bb0ab1d6200cc8afeb3df60fa7558a72a5eafd5ebaa1b8037a7fe6b1480d84ba2956fb9ff03f6e7a217938891eec26c473679f9511c401d8bd8ca141c959ab36bf68506723c79d312f1f742c541c361693ad4c7c4a155251aa83a1cf4f66c75d67a62ecca5d8bf20a4aff793f318c137753614de405ebcf5bef87d1c98f9c67b56303b7117dade53df61a6485b93de0060ceadeeedc52fff44bbb090bee1c5f3548746dee9086050e9f299bad6d7b95650ad4c09379f9c8078c9b0a4f71de0f8d1337d90ace96f47528122343199fd1cc99869ee97e992ea3a1155def705eebde21343034028f3bfe840057f878a98a6d3a5d3e4a4af33c22c6bf5ba2a92fd3dad99aa77ef140f66d04ced4ee345f659a6f906de4c6e9c63fa4dbf6cd004b2cfbcb3b0193b5fc954493ea252d8a1a66485c536dcc567f5c8213aa3e19d2c4d4989d09ac4e72006d70650b8c807465506c6ed251b08ab02d21e511f5dccdbc78e1cfcc8656620c2ce3a782fd22da14403dab56c2026b6e830849664e223f496ac26924b0d7a9a7cba2186a6991cefcae84f1dfddf97e67934e4a0b6523c13d0cbab4735ec247c5869ffd4400781441977f8db80c1ff86aa691648f43085a03bb3e1d628f062ad3f1c40f0a7503240b54012052c67674bdbbc38f19441a16f3e3c54e0469f2b2535b54db19e3150e0e3e672f0183615e6fb1e6d75b2e3723d3f4f2f41fa93d6b1d60506fce5bf2501f15464e8387a5c00680c8d38eb54306339f0db232ac2195824ac8a62f5020b2de0ec6ec3622de6239b1dfd0528a992d64b09637cf3f16eac6a4ad5eb917cfab22bfc41571f8a13896cb3abfd0e30be09982bf1e9035a04eb49395756f6c4bdf8e30c2f0fede282f1377d708731a1fbce5b100ca251db5d186469f315cc7b0b4618d994a4f4bc0cdd53951395154b4fe705081a43d623b238c914ed8514777cace43de184cebe8632ebdb55bbbfad52a10d50a88c18236f1175041df8b1e5c093fd6f3b7ce583cbfc3a7079138124537bfd801bbfac3726532c72d3c92fb2538be27ef3c9acc6c69e4ed1e79e12244c4c3da3dcfaccd601ac7ee69e8c3a836b817b93702c5ec9e8f8d589beb839fad6ad9421d797f4c3211de8ac0aaabe620e4898495b2ef7c658a3254d3a479308e9e548ebc340eea8d72d0bb3eb9c614bb03a62b9959addda28667e274d1ce3aacf893d9f7da7322785933be4382e1b6e18dca40b5202a2c48ea845dce307eb04aa2186b80451e0c69784b64a8638fc6b6e70f2afa3f4daa2c3525666cb488d101fda7213aebaf3e19dc96f7cb486100bccf43d2cae1a5cee525dbab00aaacee64964a08c82ecfaf9cdf875373f7817c90cacfd8f7177c8ac631cc5a95365c88fdbcd468ac1f5b668ce697248304d3031300d06096086480165030402010500042001acb965b2a4e3c5400f6564045022c2b531199c90d9c33b01658165da61fd520414b296d471339ab4ba77a3329074e006d39440eb9702022710",
                        "IOTLeelenBKS3451qaz")

                    # Create SSL context (simplified - actual implementation would need proper cert handling)
                    # context = ssl.create_default_context()
                    # context.check_hostname = False
                    # context.verify_mode = ssl.CERT_NONE

                    # Create socket and connect
                    LogUtils.d(self.tag,"start socket.socket")
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.m_socket = context.wrap_socket(sock, server_hostname=self.server_host, server_side=False)
                    # self.m_socket.settimeout(5)
                    self.m_socket.connect((self.server_host, self.server_port))
                    self.m_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                    LogUtils.d(self.tag,"end socket.socket")

                    if not self.m_socket:
                        if self.show_log:
                            LogUtils.d(self.tag,f"Socket creation failed")
                        self.set_connect_state(ConnectState.NONE)
                        self.reset()
                        return

                    if self.m_socket and self.m_socket.fileno() != -1:  # Check if connected
                        try:
                            LogUtils.d(self.tag,f"{self.m_recv_data_running} start r_recv_data thread")
                            self.m_output_stream = self.m_socket.makefile('wb')
                            self.set_connect_state(ConnectState.CONNECTED)

                            # if not self.m_recv_data_running:
                            # LogUtils.d(self.tag,f"start r_recv_data thread")

                            # self.thread_pool.submit(self.r_recv_data)
                            # DefaultThreadPool.get_instance().execute(self.r_recv_data)
                            self.stop_recv_data_executor()

                            if not self.recv_data_executor or self.recv_data_executor.finished.is_set():
                                self.recv_data_executor = threading.Thread(target=self.r_recv_data)
                                self.recv_data_executor.finished = threading.Event()
                                self.recv_data_executor.start()
                                LogUtils.d(self.tag,f"r_recv_data thread started")
                            
                            self.heartbeat_once()
                            
                            # threading.Thread(target=self.r_recv_data).start()

                        except Exception as e:
                            if self.show_log:
                                LogUtils.d(self.tag,f"Error getting output stream: {e}")
                            self.set_connect_state(ConnectState.NONE)
                            self.reset()
                    else:
                        self.set_connect_state(ConnectState.NONE)
                        self.reset()

                    # self.conn_handler.send_empty_message(self.MSG_TYPE_CONNECT_RESULT)

                except Exception as e:
                    if self.show_log:
                        LogUtils.d(self.tag,f"Connection error: {e}")
                    self.set_connect_state(ConnectState.NONE)
                    self.reset()
                finally:
                    LogUtils.i(f"connect thread finished! ")
                    run.running = False

        def is_running() -> bool:
            return run.running if hasattr(run, 'running') else False

        def stop():
            run.running = False
            if self.m_socket:
                try:
                    self.m_socket.close()
                except Exception as e:
                    if self.show_log:
                        LogUtils.d(self.tag,f"Error closing socket: {e}")
                self.m_socket = None

        run.is_running = is_running
        run.stop = stop
        return run

    def _recv_data_runnable(self) -> Callable:
        def run():
            with self.recv_lock:
                if self.m_recv_data_running:
                    return
                self.m_recv_data_running = True

            try:
                if self.m_socket:
                    with self.socket_lock:
                        # 设置socket为非阻塞模式，避免recv()调用阻塞
                        try:
                            self.m_socket.settimeout(0.5)  # 设置0.5秒超时
                        except Exception as e:
                            LogUtils.d(self.tag,f"Set socket timeout error: {e}")
                        
                        while self.m_recv_data_running:
                            try:
                                data = self.m_socket.recv(4096)
                                if data:
                                    self.handle_recv_data(data)
                                else:
                                    continue
                            except BlockingIOError:
                                # 非阻塞模式下没有数据可读，继续循环
                                continue
                            except TimeoutError:
                                # 超时异常，继续循环
                                continue
                        LogUtils.i(self.tag,f"recv_data_runnable() exit")
            except Exception as e:
                with threading.Lock():
                    self.m_recv_data_running = False
                if self.show_log:
                    LogUtils.e(self.tag,f"Receive data error: {e}")
                # 在接收数据出错时重启连接
                self.reset()
            finally:
                with threading.Lock():
                    self.m_recv_data_running = False

        return run

    def close(self):
        pass
        # self.stop_heartbeat()
        # self.thread_pool.submit(self.reset)

    def connect(self):
        try:
            if self.m_connecting_count >= self.MAX_CONNECTING_COUNT:
                self.r_connect.stop()

            if self.r_connect.is_running():
                self.m_connecting_count += 1
                if self.show_log:
                    LogUtils.d(self.tag,f"Connection attempt {self.m_connecting_count}")
            else:
                self.m_connecting_count = 0
                # LogUtils.d(self.thread_pool._shutdown)
                # LogUtils.d(self.thread_pool._threads)
                # LogUtils.d(self.thread_pool._work_queue.qsize())
                # DefaultThreadPool.get_instance().execute(self.r_connect)
                # threading.Thread(target=self.r_connect).start()

                # self.thread_pool.submit(self.r_connect)
                if not self.connect_executor or self.connect_executor.finished.is_set():
                    self.connect_executor = threading.Thread(target=self.r_connect)
                    self.connect_executor.finished = threading.Event()
                    self.connect_executor.start()
        except Exception as e:
            if self.show_log:
                LogUtils.d(self.tag,f"Connect error: {e}")

    def connect_lan(self):
        if self.get_connect_state() == ConnectState.NONE:
            self.server_host = GatewayInfo.get_instance().get_lan_address_ip()
            self.connect()

    def create_heartbeat_data(self) -> bytes:
        """Abstract method to be implemented by subclasses"""
        raise NotImplementedError()

    def get_connect_state(self) -> ConnectState:
        return self.m_connect_state

    def get_logon_state(self) -> LogonState:
        return self.m_logon_state

    def handle_recv_data(self, data: bytes):
        """Abstract method to be implemented by subclasses"""
        raise NotImplementedError()

    def heartbeat_once(self):
        LogUtils.d(self.tag,f"Heartbeat once")
        self.heartbeat_data = self.create_heartbeat_data()
        # self.thread_pool.submit(self.r_heartbeat)
        # DefaultThreadPool.get_instance().execute(self.r_heartbeat)
        threading.Thread(target=self.r_heartbeat).start()

    def is_available(self) -> bool:
        if self.m_socket and self.m_socket.fileno() != -1:
            with self.socket_lock:
                try:
                    # Test connection by sending urgent data
                    self.m_socket.send(b'\xFF', socket.MSG_OOB)
                    return True
                except Exception as e:
                    if self.show_log:
                        LogUtils.d(self.tag,f"Connection test failed: {e}")
                    return False
        return False

    def is_logged_on(self) -> bool:
        return self.get_logon_state() == LogonState.LOGGED_ON

    def logon(self):
        if self.get_connect_state() == ConnectState.CONNECTED:
            if LogonState.NONE == self.get_logon_state():
                self.send_logon_data()
            else:
                if self.show_log:
                    LogUtils.d(self.tag,f"Already logging in or logged in")
        else:
            self.connect()

    def on_connect_result(self, success: bool):
        """Abstract method to be implemented by subclasses"""
        raise NotImplementedError()

    def on_server_host_empty(self):
        """Abstract method to be implemented by subclasses"""
        raise NotImplementedError()

    def open(self):
        if self.scheduled_executor and not self.scheduled_executor.finished.is_set():
            self.heartbeat_once()
            LogUtils.d(self.tag,f"Heartbeat once")
        else:
            self.start_heartbeat()
            LogUtils.d(self.tag,f"Started heartbeat")

    def recv_heartbeat(self):
        self.pre_heartbeat_recv = True
        self.pre_heartbeat_recv_time = time.time()

    def reset(self):
        LogUtils.w(self.tag,f"Reset connection")
        
        # 1. 停止所有运行的线程
        self.m_recv_data_running = False
        # self.stop_heartbeat()
        self.stop_connect_executor()
        self.stop_recv_data_executor()
        
        # 2. 关闭socket和流
        if self.m_socket:
            try:
                self.m_socket.close()
                LogUtils.d(self.tag,f"Socket closed")
            except Exception as e:
                if self.show_log:
                    LogUtils.d(self.tag,f"Close socket error: {e}") 
            self.m_socket = None
        
        if hasattr(self, 'm_output_stream') and self.m_output_stream:
            try:
                self.m_output_stream.close()
                LogUtils.d(self.tag,f"Output stream closed")
            except Exception as e:
                if self.show_log:
                    LogUtils.d(self.tag,f"Close output stream error: {e}") 
            self.m_output_stream = None
        
        # 3. 重置状态
        self.set_connect_state(ConnectState.NONE)
        self.set_logon_state(LogonState.NONE)
        self.connect_retry_count = 0
        self.pre_heartbeat_recv = False
        self.pre_heartbeat_recv_time = -1
        self.pre_heartbeat_start_time = time.time()
        self.pre_heartbeat_send_time = -1
        
        LogUtils.d(self.tag,f"Reset completed, preparing to reconnect")
        
        # 4. 自动重新连接
        try:
            LogUtils.d(self.tag,f"Calling connect_lan()")
            self.connect_lan()
        except Exception as e:
            LogUtils.e(self.tag,f"Error during reconnect: {e}")
        
        # 5. 确保心跳线程重新启动
        try:
            self.start_heartbeat()
        except Exception as e:
            LogUtils.e(self.tag,f"Error starting heartbeat: {e}")
        

    def send_data(self, data: bytes):
        if data is None:
            return

        if self.show_log:
            LogUtils.d("📤 Sending data",f"{data.hex()}")
        
        if self.m_socket and self.get_connect_state() == ConnectState.CONNECTED:
            def send_task():
                try:
                    with self.send_lock:
                        self.m_socket.sendall(data)
                except Exception as e:
                    if self.show_log:
                        LogUtils.d(self.tag,f"Send data error: {e}")
                    # 当遇到Broken pipe等错误时，重置连接
                    if isinstance(e, (ConnectionResetError, BrokenPipeError, OSError)):
                        LogUtils.w(self.tag,f"Connection error, resetting: {e}")
                        self.reset()
                        # 如果是ConnectLan实例，调用connect_lan
                        if hasattr(self, 'connect_lan'):
                            self.connect_lan()
                        # 否则调用connect
                        else:
                            self.connect()
                            LogUtils.i(self.tag,f"Calling connect()")
            # 使用线程池执行发送任务，避免线程泄漏
            DefaultThreadPool.get_instance().execute(send_task)
        else:
            LogUtils.i(self.tag,f"Socket not ready or not connected, resetting")
            self.reset()
            # 如果是ConnectLan实例，调用connect_lan
            if hasattr(self, 'connect_lan'):
                self.connect_lan()
            # 否则调用connect
            else:
                self.connect()

    def send_heartbeat(self, data: bytes):
        if self.get_connect_state() == ConnectState.NONE:
            self.connect()
        elif self.get_connect_state() != ConnectState.CONNECTING:
            if self.get_logon_state() == LogonState.NONE:
                self.logon()
            elif self.get_logon_state() != LogonState.LOGGING_ON:
                # if not self.pre_heartbeat_recv:
                # 超时
                if time.time() - self.pre_heartbeat_recv_time > 30:
                # if time.time() - self.pre_heartbeat_start_time  > 150:
                    self.pre_heartbeat_start_time= time.time()
                    LogUtils.e(self.tag,f" 💥 heartbeat not recv for 30s,reset ")
                    self.reset()
                    # self.open()
                else:
                    self.send_data(data)
                    self.pre_heartbeat_recv = False
                    self.pre_heartbeat_send_time = time.time()

    def send_logon_data(self):
        """Abstract method to be implemented by subclasses"""
        raise NotImplementedError()

    def set_connect_state(self, state: ConnectState):
        self.m_connect_state = state

    def set_logon_state(self, state: LogonState):
        self.m_logon_state = state
        self.pre_heartbeat_recv = (state == LogonState.LOGGED_ON)
        if self.pre_heartbeat_recv:
            self.pre_heartbeat_recv_time = time.time()

    def start_heartbeat(self):
        self.heartbeat_data = self.create_heartbeat_data()
        LogUtils.d(self.tag,f" start_heartbeat {self.m_recv_data_running} {self.scheduled_executor} ")
        # 确保m_recv_data_running为True
        # self.m_recv_data_running = True
        
        # 检查是否已经有心跳线程在运行
        if self.scheduled_executor and not self.scheduled_executor.finished.is_set():
            LogUtils.d(self.tag,f" Heartbeat thread already running, skipping start ")
            return
        
        # 停止现有的心跳线程
        # self.stop_heartbeat()
        
        # 确保scheduled_executor为None
        if self.scheduled_executor:
            LogUtils.d(self.tag,f" Waiting for existing heartbeat thread to stop ")
            try:
                self.scheduled_executor.join(timeout=1.0)
            except Exception as e:
                LogUtils.d(self.tag,f" Join error: {e}")
        
        # 创建新的心跳线程
        def heartbeat_task():
            while not self.scheduled_executor.finished.is_set():
                try:
                    self.r_heartbeat()
                except Exception as e:
                    LogUtils.d(self.tag,f" Heartbeat task error: {e}")
                # 每次循环都检查是否需要停止
                # for i in range(int(self.heartbeat_interval * 10)):
                #     if not self.m_recv_data_running or self.scheduled_executor.finished.is_set():
                #         break
                #     time.sleep(0.1)
                time.sleep(self.heartbeat_interval)
            LogUtils.d(self.tag,f" 💥 stoped heartbeat_task ")

        # 双重检查，确保不会重复创建
        if not self.scheduled_executor or self.scheduled_executor.finished.is_set():
            self.scheduled_executor = threading.Thread(target=heartbeat_task)
            self.scheduled_executor.finished = threading.Event()
            self.scheduled_executor.start()
            LogUtils.d(self.tag,f" 💥 heartbeat_task started ")
        else:
            LogUtils.d(self.tag,f" Heartbeat thread already exists, skipping start ")
            # self.thread_pool.submit(heartbeat_task)
            # DefaultThreadPool.get_instance().execute(heartbeat_task)

    def stop_heartbeat(self):
        if self.scheduled_executor and not self.scheduled_executor.finished.is_set():
            self.scheduled_executor.finished.set()
            # 等待线程真正停止，最多等待2秒
            try:
                self.scheduled_executor.join(timeout=2.0)
                LogUtils.d(self.tag,f" 💥 scheduled_executor joined ")
            except Exception as e:
                LogUtils.d(self.tag,f" Join scheduled_executor error: {e}")
            self.scheduled_executor = None
            LogUtils.d(self.tag,f" 💥 scheduled_executor stoped ")

    def stop_connect_executor(self):
        if self.connect_executor and not self.connect_executor.finished.is_set():
            self.connect_executor.finished.set()
            # 等待线程真正停止，最多等待2秒
            try:
                self.connect_executor.join(timeout=2.0)
                LogUtils.d(self.tag,f" 💥 connect_executor joined ")
            except Exception as e:
                LogUtils.d(self.tag,f" Join connect_executor error: {e}")
            self.connect_executor = None
            LogUtils.d(self.tag,f" 💥 stop_connect_executor stoped ")

    def stop_recv_data_executor(self):
        if self.recv_data_executor and not self.recv_data_executor.finished.is_set():
            # 1. 设置停止信号
            self.recv_data_executor.finished.set()
            
            # 2. 设置m_recv_data_running为False
            with threading.Lock():
                self.m_recv_data_running = False
            
            # 3. 关闭socket，唤醒阻塞的recv()调用
            if self.m_socket:
                try:
                    self.m_socket.close()
                    LogUtils.d(self.tag,f" Socket closed to wake up recv() ")
                except Exception as e:
                    LogUtils.d(self.tag,f" Error closing socket: {e}")
            
            # 4. 等待线程真正停止，最多等待2秒
            try:
                self.recv_data_executor.join(timeout=2.0)
                LogUtils.d(self.tag,f" 💥 recv_data_executor joined ")
            except Exception as e:
                LogUtils.d(self.tag,f" Join recv_data_executor error: {e}")
            
            # 5. 清理
            self.recv_data_executor = None
            LogUtils.d(self.tag,f" 💥 stop_recv_data_executor stoped ")
    
    

