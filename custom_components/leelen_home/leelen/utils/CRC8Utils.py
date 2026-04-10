class CRC8Utils:
    SHIFT_DATA = [
        0, -2, -1, 1, -3, 3, 2, -4, -7, 7, 6, -8, 4, -6, -5, 5,
        -15, 15, 14, -16, 12, -14, -13, 13, 8, -10, -9, 9, -11, 11, 10, -12,
        -31, 31, 30, -32, 28, -30, -29, 29, 24, -26, -25, 25, -27, 27, 26, -28,
        16, -18, -17, 17, -19, 19, 18, -20, -23, 23, 22, -24, 20, -22, -21, 21,
        -63, 63, 62, -64, 60, -62, -61, 61, 56, -58, -57, 57, -59, 59, 58, -60,
        48, -50, -49, 49, -51, 51, 50, -52, -55, 55, 54, -56, 52, -54, -53, 53,
        32, -34, -33, 33, -35, 35, 34, -36, -39, 39, 38, -40, 36, -38, -37, 37,
        -47, 47, 46, -48, 44, -46, -45, 45, 40, -42, -41, 41, -43, 43, 42, -44,
        -127, 127, 126, -128, 124, -126, -125, 125, 120, -122, -121, 121, -123, 123, 122, -124,
        112, -114, -113, 113, -115, 115, 114, -116, -119, 119, 118, -120, 116, -118, -117, 117,
        96, -98, -97, 97, -99, 99, 98, -100, -103, 103, 102, -104, 100, -102, -101, 101,
        -111, 111, 110, -112, 108, -110, -109, 109, 104, -106, -105, 105, -107, 107, 106, -108,
        64, -66, -65, 65, -67, 67, 66, -68, -71, 71, 70, -72, 68, -70, -69, 69,
        -79, 79, 78, -80, 76, -78, -77, 77, 72, -74, -73, 73, -75, 75, 74, -76,
        -95, 95, 94, -96, 92, -94, -93, 93, 88, -90, -89, 89, -91, 91, 90, -92,
        80, -82, -81, 81, -83, 83, 82, -84, -87, 87, 86, -88, 84, -86, -85, 85
    ]

    @staticmethod
    def calc_shift_val(data: bytes, length: int) -> int:
        """
        Calculate the shift value for CRC8 calculation
        
        Args:
            data: Input data bytes
            length: Number of bytes to process
            
        Returns:
            Calculated shift value
        """
        shift_val = 0
        for i in range(length):
            shift_val = CRC8Utils._get_shift_val(shift_val, data[i])
        return shift_val % 256

    @staticmethod
    def _get_shift_val(current_val: int, byte_val: int) -> int:
        """
        Get the next shift value from the lookup table
        
        Args:
            current_val: Current shift value
            byte_val: Next byte value
            
        Returns:
            Next shift value from the lookup table
        """
        index = (current_val ^ byte_val) & 0xFF
        return CRC8Utils.SHIFT_DATA[index]
