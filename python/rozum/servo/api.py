import os
import logging
import platform
from ctypes import *

from .constants import RET_OK, RET_STATUS_MESSAGE

__all__ = ["ServoApi", "ServoError", "logger"]


logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())
# TODO rr_setup_nmt_callback, rr_setup_emcy_callback
# TODO normal logging
# TODO write doc strings with references
# TODO tests


class ServoError(Exception):
    def __init__(self, code, message):
        self.status = code
        super(ServoError, self).__init__(message)

    @staticmethod
    def handle(code):
        if code == RET_OK:
            return

        else:
            raise ServoError(code, RET_STATUS_MESSAGE[code])


class EmcyObject(Structure):
    _fields_ = [
        ("id", c_uint8),
        ("code", c_uint16),
        ("registry", c_uint8),
        ("bits", c_uint8),
        ("info", c_uint32)
    ]


class _Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(_Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class Servo(object):
    def __init__(self, library_api, servo_interface, identifier):
        self._api = library_api
        self._servo = servo_interface
        self._identifier = identifier

    @property
    def interface(self):
        return self._servo

    @property
    def identifier(self):
        return self._identifier

    def param_cache_setup_entry(self, param: int, enabled: bool):
        """The function is the fist one in the API call sequence that enables reading multiple servo parameters
        (e.g., velocity, voltage, and position) as a data array.

        Using the sequence is advisable when you need to read more than one parameter at a time.
        The user can set up the array to include up to 50 parameters.
        In all, the sequence comprises the following functions:
            * param_cache_setup_entry for setting up an array of servo parameters to read
            * param_cache_update for retrieving the parameters from the servo and saving them to the program cache
            * read_cached_parameter for reading parameters from the program cache

        Using the sequence of API calls allows for speeding up data acquisition by nearly two times.
        Let's assume you need to read 49 parameters. At a bit rate of 1 MBit/s, reading them one by one will take about
        35 ms, whereas reading them as an array will only take 10 ms.

        :param param: int:
            Index of the parameter to read as indicated in the rr_servo_param_t list (e.g., APP_PARAM_POSITION_ROTOR) TODO refactor parameters
        :param enabled: bool
            Set True/False to enable/ disable the specified parameter for reading
        :return: None
        """
        status = self._api.rr_param_cache_setup_entry(self._servo, c_int(param), c_bool(enabled))
        ServoError.handle(status)

    def param_cache_update(self):
        """The function is always used in combination with the param_cache_setup_entry function.
        It retrieves from the servo the array of parameters set up using the param_cache_setup_entry function and saves
        the array to the program cache. You can subsequently read the parameters from the program cache with the
        read_cached_parameter function. For more information, see param_cache_setup_entry.

        **Note:** After you exit the program, the cache is cleared.

        :return: None
        """
        status = self._api.rr_param_cache_update(self._servo)
        ServoError.handle(status)

    def read_cached_parameter(self, param: int):
        """The function is always used in combination with the param_cache_setup_entry and the param_cache_update
        functions. For more information, see rr_param_cache_setup_entry.

        The function enables reading parameters from the program cache. If you want to read more than one parameter,
        you will need to make a separate API call for each of them.

        **Note:** Prior to reading a parameter, make sure to update the program cache using the param_cache_update
        function.

        :param param: int
            Index of the parameter to read; you can find these indices in the rr_servo_param_t list
            (e.g., APP_PARAM_POSITION_ROTOR)
        :return: Requested value: float
        """
        value = c_float()
        status = self._api.rr_read_cached_parameter(self._servo, c_int(param), byref(value))
        ServoError.handle(status)
        return value.value

    def read_parameter(self, param: int):
        """The function enables reading a single parameter directly from the servo. The function returns the current
        value of the parameter. Additionally, the parameter is saved to the program cache, irrespective of whether it
        was enabled/ disabled with the param_cache_setup_entry function.

        :param param: int:
            Index of the parameter to read; you can find these indices in the rr_servo_param_t list
            (e.g., APP_PARAM_POSITION_ROTOR)
        :return: Requested value: float
        """
        value = c_float()
        status = self._api.rr_read_parameter(self._servo, c_int(param), byref(value))
        ServoError.handle(status)
        return value.value

    def get_max_velocity(self):
        """The function reads the maximum velocity of the servo at the current moment. It returns the smallest of the
        three values—the user-defined maximum velocity limit (set_max_velocity), the maximum velocity value based on
        the servo specifications, or the calculated maximum velocity based on the supply voltage.

        :return: Maximum servo velocity (in degrees/sec): float
        """
        velocity = c_float()
        status = self._api.rr_get_max_velocity(self._servo, byref(velocity))
        ServoError.handle(status)
        return velocity.value

    def set_max_velocity(self, max_velocity_deg_per_sec: float):
        """The function sets the maximum velocity limit for the servo.
        The setting is volatile: after a reset or a power outage, it is no longer valid.

        :param max_velocity_deg_per_sec: float:
            Velocity at the servo flange (in degrees/sec)
        :return: None
        """
        status = self._api.rr_set_max_velocity(self._servo, c_float(max_velocity_deg_per_sec))
        ServoError.handle(status)

    def set_zero_position(self, position_deg: float):
        """The function enables setting the current position (in degrees) of the servo to any value defined by the user.

        For instance, when the current servo position is 101 degrees and the 'position_deg' parameter is set to
        25 degrees, the servo is assumed to be positioned at 25 degrees.

        :param position_deg: float:
            User-defined position (in degrees) to replace the current position value
        :return: None
        """
        status = self._api.rr_set_zero_position(self._servo, c_float(position_deg))
        ServoError.handle(status)

    def set_zero_position_and_save(self, position_deg: float):
        """The function enables setting the current position (in degrees) of the servo to any value defined by the user
        and saving it to the FLASH memory. If you don't want to save the newly set position, use the set_zero_position
        function.

        **Note:The FLASH memory limit is 1,000 write cycles.
        Therefore, it is not advisable to use the function on a regular basis.**

        :param position_deg: float:
            User-defined position (in degrees) to replace the current position value
        :return: None
        """
        status = self._api.rr_set_zero_position_and_save(self._servo, c_float(position_deg))
        ServoError.handle(status)

    def add_motion_point(self, position_deg: float, velocity_deg_per_sec: float, time_ms: int,
                         accel_deg_per_sec2: float = None):
        """The function enables creating PVT (position-velocity-time) points to set a motion trajectory of the servo.

        PVT points define the following:
            * what position the servo specified in the 'servo' parameter should reach
            * how fast the servo should move to the specified position
            * how long the movement to the specified position should take

        Created PVT points are arranged into a motion queue that defines the motion trajectory of the specified servo.
        To execute the motion queue, use the Interface.start_motion() function.

        :param position_deg: float:
            Position that the servo flange (in degrees) should reach as a result of executing the command
        :param velocity_deg_per_sec: float:
            Velocity(in degrees/sec) at which the servo should move to reach the specified position
        :param time_ms: int:
            Time (in milliseconds) it should take the servo to move from the previous position
            (PVT point in a motion trajectory or an initial point) to the commanded one.
            The maximum admissible value is (2^32-1)/10 (roughly equivalent to 4.9 days).
        :param accel_deg_per_sec2: float
            Acceleration (in degrees/sec**2) which the servo should have in the position where it comes.
        :return: None
        """
        if accel_deg_per_sec2 is not None:
            status = self._api.rr_add_motion_point_pvat(
                self._servo,
                c_float(position_deg),
                c_float(velocity_deg_per_sec),
                c_float(accel_deg_per_sec2),
                c_uint32(time_ms)
            )
        else:
            status = self._api.rr_add_motion_point(
                self._servo, c_float(position_deg), c_float(velocity_deg_per_sec), c_uint32(time_ms)
            )
        ServoError.handle(status)

    def clear_points(self, num_to_clear: int):
        """The function removes the number of PVT points indicated in the 'num_to_clear' parameter from the tail of the
        motion queue preset for the servo. When the indicated number of PVT points to be removed exceeds the actual
        remaining number of PVT points in the queue, the funtion clears only the actual remaining number of PVT points.

        :param num_to_clear: int:
            Number of PVT points to be removed from the motion queue of the specified servo
        :return: None
        """
        status = self._api.rr_clear_points(self._servo, c_uint32(num_to_clear))
        ServoError.handle(status)

    def clear_points_all(self):
        """The function clears the entire motion queue of the servo. The servo completes the move it started before the
        function call and then clears all the remaining PVT points in the queue.

        :return: None
        """
        status = self._api.rr_clear_points_all(self._servo)
        ServoError.handle(status)

    def get_points_free_space(self):
        """The function returns how many more PVT points the user can add to the motion queue of the servo.

        **Note:** Currently, the maximum motion queue size is 100 PVT.

        :return: Number of free points: int
        """
        size = c_uint32(0)
        status = self._api.rr_get_points_free_space(self._servo, byref(size))
        ServoError.handle(status)
        return size.value

    def get_points_size(self):
        """The function returns the actual motion queue size of the specified servo.
        The return value indicates how many PVT points have already been added to the motion queue.

        :return: Number of points in motion queue: int
        """
        size = c_uint32(0)
        status = self._api.rr_get_points_size(self._servo, byref(size))
        ServoError.handle(status)
        return size.value

    def invoke_time_calculation(self,
                                start_position: float, start_velocity_deg_per_sec: float,
                                start_acceleration_deg_per_sec2: float, start_time_ms: int,
                                end_position: float, end_velocity_deg_per_sec: float,
                                end_acceleration_deg_per_sec2: float, end_time_ms: int):
        """The function enables calculating the time it will take for the servo to get from one position to another at
        the specified motion parameters (e.g., velocity, acceleration).

        **Note:** The function is executed without the servo moving.

        :param start_position: float:
            Position (in degrees) from where the specified servo should start moving
        :param start_velocity_deg_per_sec: float:
            Servo velocity (in degrees/sec) at the start of motion
        :param start_acceleration_deg_per_sec2: float:
            Servo acceleration (in degrees/sec^2) at the start of motion
        :param start_time_ms: int:
            Initial time setting (in milliseconds)
        :param end_position: float:
            Position (in degrees) where the servo should arrive
        :param end_velocity_deg_per_sec: float:
            Servo velocity (in degrees/sec) in the end of motion
        :param end_acceleration_deg_per_sec2: float:
            Servo acceleration (in degrees/sec^2) in the end of motion
        :param end_time_ms: int
            Final time setting (in milliseconds)
        :return: Calculated time in ms: int
        """
        calculated_time = c_uint32(0)
        status = self._api.rr_invoke_time_calculation(self._servo,
                                                      c_float(start_position), c_float(start_velocity_deg_per_sec),
                                                      c_float(start_acceleration_deg_per_sec2), c_uint32(start_time_ms),
                                                      c_float(end_position), c_float(end_velocity_deg_per_sec),
                                                      c_float(end_acceleration_deg_per_sec2), c_uint32(end_time_ms),
                                                      byref(calculated_time))
        ServoError.handle(status)
        return calculated_time.value

    def brake_engage(self, en: bool):
        """The function applies or releases servo's built-in brake (if installed).

        :param en: bool: Desired action: True - engage brake, False - disengage
        :return: None
        """
        status = self._api.rr_brake_engage(self._servo, c_bool(en))
        ServoError.handle(status)

    def release(self):
        """The function sets the specified servo to the released state. The servo is de-energized and stops without
        retaining its position.

        **Note:** When there is an external force affecting the servo (e.g., inertia, gravity), the servo may continue
        rotating or begin rotating in the opposite direction.

        :return: None
        """
        status = self._api.rr_release(self._servo)
        ServoError.handle(status)

    def freeze(self):
        """The function sets the specified servo to the freeze state. The servo stops, retaining its last position.

        :return: None
        """
        status = self._api.rr_freeze(self._servo)
        ServoError.handle(status)

    def set_current(self, current_a: float):
        """The function sets the current supplied to the stator of the servo specified in the 'servo' parameter.
        Changing the 'current_a parameter' value, it is possible to adjust the servo's torque.

        Torque = stator current*Kt.

        :param current_a: float:
            Phase current of the stator in Amperes
        :return: None
        """
        status = self._api.rr_set_current(self._servo, c_float(current_a))
        ServoError.handle(status)

    def set_duty(self, duty_percent: float):
        """The function limits the input voltage supplied to the servo, enabling to adjust its motion velocity.

        For instance, when the input voltage is 20V, setting the duty_percent parameter to 40% will result in 8V
        supplied to the servo.

        :param duty_percent: float:
            User-defined percentage of the input voltage to be supplied to the servo
        :return: None
        """
        status = self._api.rr_set_duty(self._servo, c_float(duty_percent))
        ServoError.handle(status)

    def set_position(self, position_deg: float):
        """The function sets the position that the servo should reach as a result of executing the command.

        The velocity and current are maximum values in accordance with the servo motor specifications.
        For setting lower velocity and current limits, use the set_position_with_limits function.

        :param position_deg: float:
            Position of the servo (in degrees) to be reached.
            The parameter is a multi-turn value (e.g., when set to 720, the servo will make two turns, 360 degrees each).
            When the parameter is set to a "-" sign value, the servo rotates in the opposite direction.
        :return: None
        """
        status = self._api.rr_set_position(self._servo, c_float(position_deg))
        ServoError.handle(status)

    def set_position_with_limits(self, position_deg: float, velocity_deg_per_sec: float, accel_deg_per_sec_sq: float):
        """The function sets the position that the servo should reach with velocity and acceleration limits on generated trajectory.

        :param position_deg: float:
            Final position of the servo flange (in degrees) to be reached
        :param velocity_deg_per_sec: float:
            Maximum Velocity on generated trajectory (in degrees/sec)
        :param accel_deg_per_sec_sq:
            Maximum acceleration on generated trajectory (in degrees/(sec*sec))
        :return: Trajectory execution time (im milliseconds): int
        """
        time_ms = c_uint32()
        status = self._api.rr_set_position_with_limits(self._servo,
                                              c_float(position_deg),
                                              c_float(velocity_deg_per_sec),
                                              c_float(accel_deg_per_sec_sq),
                                              byref(time_ms))
        ServoError.handle(status)
        return int(time_ms.value)

    def set_velocity_motor(self, velocity_rpm: float):
        """The function sets the velocity with which the motor of the specified
         servo should move at its maximum current. The maximum current is in
         accordance with the servo motor specification. You can use the
         function for both geared servos and servos without a gearhead. When a
         servo is geared, the velocity at the output flange will depend on the
         applied gear ratio(refer to the servo motor specification).

        :param velocity_rpm Velocity of the motor (in revolutions per minute)
        :return: None
        """
        status = self._api.rr_set_velocity_motor(
            self._servo, c_float(velocity_rpm)
        )
        ServoError.handle(status)

    def set_velocity(self, velocity_deg_per_sec: float):
        """The function sets the velocity at which the servo should move at its maximum current.
        The maximum current is in accordance with the servo motor specification.

        When you need to set a lower current limit, use the set_velocity_with_limits function.

        :param velocity_deg_per_sec: float:
            Velocity (in degrees/sec) at the servo flange
        :return: None
        """
        status = self._api.rr_set_velocity(self._servo, c_float(velocity_deg_per_sec))
        ServoError.handle(status)

    def set_velocity_with_limits(self, velocity_deg_per_sec: float, current_a: float):
        """The function commands the servo to rotate at the specified velocity, while setting the maximum
        limit for the servo current (below the servo motor specifications).

        :param velocity_deg_per_sec: float:
            Velocity (in degrees/sec) at the servo flange. The value can have a "-" sign, in which case the servo will
            rotate in the opposite direction
        :param current_a: float:
            Maximum user-defined current limit in Amperes.
        :return: None
        """
        status =self._api.rr_set_velocity_with_limits(
            self._servo, c_float(velocity_deg_per_sec), c_float(current_a)
        )
        ServoError.handle(status)

    def reboot(self):
        """The function reboots the servo, resetting it to the power-on state.

        :return: None
        """
        status = self._api.rr_servo_reboot(self._servo)
        ServoError.handle(status)

    def reset_communication(self):
        """The function resets communication on the servo without resetting the entire interface.

        :return: None
        """
        status = self._api.rr_servo_reset_communication(self._servo)
        ServoError.handle(status)

    def set_state_operational(self):
        """The function sets the servo to the operational state. In the state, the servo is both available
        for communication and can execute commands.

        For instance, you may need to call the function to switch the servo from the pre-operational state to the
        operational one after an error (e.g., due to overcurrent).

        :return: None
        """
        status = self._api.rr_servo_set_state_operational(self._servo)
        ServoError.handle(status)

    def set_state_pre_operational(self):
        """The function sets the servo to the pre-operational state. In the state, the servo is available for
        communication, but cannot execute any commands.

        For instance, you may need to call the function, if you want to force the servo to stop executing commands,
        e.g., in an emergency.

        :return: None
        """
        status = self._api.rr_servo_set_state_pre_operational(self._servo)
        ServoError.handle(status)

    def set_state_stopped(self):
        """The function sets the servo to the stopped state. In the state, only Heartbeats are available.
        You can neither communicate with the servo nor make it execute any commands.

        For instance, you may need to call the fuction to reduce the workload of a CAN bus by disabling individual
        servos connected to it without deninitializing them.

        :return: None
        """
        status = self._api.rr_servo_set_state_stopped(self._servo)
        ServoError.handle(status)

    def read_error_status(self, array_size: int):
        """The functions enables reading the total actual count of servo hardware errors
        (e.g., no Heartbeats/overcurrent, etc.). In addition, the function returns the codes of all detected errors
        as a single array.

        **Note:** The rr_ret_status_t codes returned by API functions only indicate that an error occured during
        communication between the user program and a servo. If it is a hardware error, the rr_ret_status_t code will be
        RET_ERROR. Use read_error_status to determine the cause of the error.

        :param array_size:
            Array size where the function will save the codes of all errors.
            Default array size is ARRAY_ERROR_BITS_SIZE **Note:** Call the describe_emcy_bit function, to get a detailed
            error code description. If the array is not used, set the parameter to 0.
        :return: (Error count, Error array): (int, list)
        """
        error_count = c_uint32(0)
        error_array = (c_uint8 * array_size)()
        status = self._api.rr_read_error_status(
            self._servo, byref(error_count), byref(error_array)
        )
        ServoError.handle(status)
        return error_count.value, error_array

    def get_version(self):
        """The function returns hardware and software version of the device.

        Example: {
            "hardware": {
                "serial": "590370f_51363432_363130",
                "type": "52",
                "rev": "36",
            },
            "software": {
                "major": "10",
                "minor": "36",
                "timestamp": "20180329_120556",
            }
        }

        :return: dict with data like in example: dict
        """
        buffer_size = 100
        hardware_version = create_string_buffer(buffer_size)
        soft_version = create_string_buffer(buffer_size)
        status = self._api.rr_get_hardware_version(
            self._servo, hardware_version, byref(c_int(buffer_size))
        )
        ServoError.handle(status)
        status = self._api.rr_get_software_version(
            self._servo, soft_version, byref(c_int(buffer_size))
        )
        ServoError.handle(status)
        hardware_data = hardware_version.value.decode("utf-8").split(".")
        software_data = soft_version.value.decode("utf-8").split(".")
        return {
            "hardware": {
                "serial": hardware_data[0],
                "type": hardware_data[1],
                "rev": hardware_data[2],
            },
            "software": {
                "major": software_data[0],
                "minor": software_data[1],
                "timestamp": software_data[2],
            }
        }

    def get_state(self):
        """The function retrieves the actual NMT state of a servo motor

        :return Device status: int
        """
        servo_state = c_int8()
        status = self._api.rr_servo_get_state(
            self._servo, byref(servo_state)
        )
        ServoError.handle(status)
        return servo_state.value

    def get_hb_stat(self):
        """The function retrieves heart-beat statistics (min & max arrival intervals).

        :return: Minimal value, Maximal value
        """
        min_inteval = c_int64()
        max_interval = c_int64()

        status = self._api.rr_servo_get_hb_stat(
            self._servo,
            byref(min_inteval),
            byref(max_interval)
        )
        ServoError.handle(status)

        return min_inteval.value, max_interval.value

    def clear_hb_stat(self):
        """The function clears heart-beat statistics (min & max arrival intervals).

        :return: None
        """
        status = self._api.rr_servo_clear_hb_stat(self._servo)
        ServoError.handle(status)

    def _write_raw_sdo(self, idx: c_uint16, sidx: c_uint8, data: c_void_p, sz: c_int, retry: c_int, tout: c_int):
        """The function performs an arbitrary SDO write request.

        :param idx: c_uint16:
            Index of SDO object
        :param sidx: c_uint8:
            Subindex
        :param data: c_void_p:
            Data to write to
        :param sz: c_int:
            Size of data in bytes
        :param retry: c_int:
            Number of retries (if communication error occurred during request)
        :param tout: c_int:
            Request timeout in milliseconds
        :return: None
        """
        status = self._api.rr_write_raw_sdo(
            self._servo, idx, sidx, data, sz, retry, tout
        )
        ServoError.handle(status)

    def _read_raw_sdo(self, idx: c_uint16, sidx: c_uint8, data: c_void_p, sz: c_int, retry: c_int, tout: c_int):
        """The function performs an arbitrary SDO read request.

        :param idx: c_uint16:
            Index of SDO object
        :param sidx: c_uint8:
            Subindex
        :param data: c_void_p:
            Array where data is saved
        :param sz: c_int:
            Size of data in bytes
        :param retry: c_int:
            Number of reties (if communication error occured during request)
        :param tout: c_int:
            Request timeout in milliseconds
        :return: status: int
        """
        status = self._api.rr_read_raw_sdo(
            self._servo, idx, sidx, data, byref(sz), retry, tout
        )
        ServoError.handle(status)


class Interface(object):

    def __init__(self, library_api, interface_name):
        self._api = library_api
        self._interface = c_void_p(self._api.rr_init_interface(
                bytes(interface_name, encoding="utf-8")
        ))
        if self._interface is None:
            message = "Failed to initialize interface by name: {}".format(
                interface_name
            )
            logger.error(message)
            raise AttributeError(message)
        self._servos = {}

    def start_motion(self, timestamp_ms: int):
        """The function commands all servos connected to the specified interface (CAN bus) to move simultaneously
        through a number of preset PVT points.

        **Note:** When any servo fails to reach any PVT point due to an error, it broadcasts a
        "Go to Stopped State" command to all the other servos on the same bus. The servos stop executing preset
        PVT points and go to the stopped state. In the state, only Heartbeats are available. You can neither communicate
        with servos nor command them to execute any operations.

        **Note:** Once servos execute the last PVT in their preset motion queue, the queue is cleared automatically.

        :param timestamp_ms: int
            Delay (in milliseconds) before the servos associated with the interface start to move.
            When the value is set to 0, the servos start moving immediately.
            The available value range is from 0 to 2^24-1.
        :return: None
        """
        status = self._api.rr_start_motion(self._interface, c_uint32(timestamp_ms))
        ServoError.handle(status)

    def init_servo(self, identifier) -> Servo:
        """The function determines whether the servo motor with the specified ID is connected to the specified interface.

         It waits for 2 seconds to receive a Heartbeat message from the servo. When the message arrives within the
         interval, the servo is identified as successfully connected.

        :param identifier: int:
            Unique identifier of the servo in the specified interface. The available value range is from 0 to 127.
        :return: Servo instance
        """
        if identifier not in self._servos:
            servo_interface = c_void_p(self._api.rr_init_servo(self._interface, c_byte(identifier)))
            if servo_interface is None:
                message = "Failed to initialize servo by id: {}".format(identifier)
                logger.error(message)
                raise AttributeError(message)
            self._servos[identifier] = Servo(self._api, servo_interface, identifier)
        return self._servos[identifier]

    def change_id_and_save(self, old_id: int, new_can_id: int):
        """The function enables changing the default CAN identifier (ID) of the specified servo to avoid collisions on
        a bus line. **Important!** Each servo connected to a CAN bus must have **a unique ID**.

        When called, the function resets CAN communication for the specified servo, checks that Heartbeats are generated
        for the new ID, and saves the new CAN ID to the EEPROM memory of the servo.

        **Note: The EEPROM memory limit is 1,000 write cycles. Therefore, it is advisable to use the function with
        discretion.**

        :param old_id: int:
            Old CAN ID.
        :param new_can_id: int:
            New CAN ID. You can set any value within the range from 1 to 127, only make sure no other servo has the same
            ID.
        :return: None
        """
        servo_interface = self.init_servo(old_id).interface
        status = self._api.rr_change_id_and_save(self._interface, byref(servo_interface), c_uint8(new_can_id))
        ServoError.handle(status)
        del self._servos[old_id]

    def net_reboot(self):
        """The function reboots all servos connected to the current interface, resetting them back to the power-on state.

        :return: None
        """
        status = self._api.rr_net_reboot(self._interface)
        ServoError.handle(status)

    def net_reset_communication(self):
        """The function resets communication on the current interface.

        For instance, you may need to use the function when changing settings that require a reset after modification.

        :return: None
        """
        status = self._api.rr_net_reset_communication(self._interface)
        ServoError.handle(status)

    def net_set_state_operational(self):
        """The function sets all servos connected to the current interface (CAN bus) to
        the operational state. In the state, servos can both communicate with the user program and execute commands.

        For instance, you may need to call the function to switch all servos on a specific bus from the pre-operational
        state to the operational one after an error (e.g., due to overcurrent).

        :return: None
        """
        status = self._api.rr_net_set_state_operational(self._interface)
        ServoError.handle(status)

    def net_set_state_pre_operational(self):
        """The function sets all servos connected to the current interface to the pre-operational state.
        In the state, servos are available for communication, but cannot execute commands.

        For instance, you may need to call the function, if you want to force all servos on a specific bus to stop
        executing commands, e.g., in an emergency.

        :return: None
        """
        status = self._api.rr_net_set_state_pre_operational(self._interface)
        ServoError.handle(status)

    def net_set_state_stopped(self):
        """The function sets all servos connected to the interface specified in the 'interface' parameter to the stopped state.
        In the state, the servos are neither available for communication nor can execute commands.

        For instance, you may need to call the fuction to stop all servos on a specific bus without deinitializing them.

        :return: None
        """
        status = self._api.rr_net_set_state_stopped(self._interface)
        ServoError.handle(status)

    def net_get_state(self, can_id: int):
        """The function retrieves the actual NMT state of any device
        (a servo motor or any other) connected to the specified CAN network.

        :param can_id: int: identificator of the addressed device
        :return Device status: int
        """
        nmt_state = c_int8()
        status = self._api.rr_net_get_state(
            self._interface, c_int(can_id), byref(nmt_state)
        )
        ServoError.handle(status)
        return nmt_state.value

    def emcy_log_get_size(self):
        """
        The function returns actual count of entries in EMCY logging buffer.

        :return: Number of unread entries :int
        """
        return self._api.rr_emcy_log_get_size(self._interface)

    def emcy_log_pop(self):
        """
        The function pops single entry from EMCY logging buffer.

        :return EmcyObject or None if no messages in buffer
        """
        emcy_object = self._api.rr_emcy_log_pop(self._interface)
        if emcy_object:
            return emcy_object.contents
        else:
            return None

    def emcy_log_clear(self):
        """The fucntion clears entire EMCY logging buffer.

        :return: None
        """
        self._api.rr_emcy_log_clear(self._interface)

    def deinit_interface(self):
        """The function closes the COM port where the corresponding CAN-USB dongle is connected, clearing all data
        associated with the interface descriptor.

        The function is called automatically when Servo API is deinitializing. In addition, it deinitializes all servos
        on the interface

        :return: None
        """
        status = self._api.rr_deinit_interface(byref(self._interface))
        ServoError.handle(status)


class ServoApi(object, metaclass=_Singleton):
    __LIB_UNIX = "libservo_api.so"
    __LIB_WIN = "libservo_api-{}.dll"

    def __init__(self):
        """The function is the first to call to be able to work with the API.
        Searches for the library in the rozum/servo directory and loads it.
        Linux: libservo_api.so
        Win32: libservo_api-32bit.dll
        Win64: libservo_api-64bit.dll

        """
        module_path = os.path.dirname(__file__)
        if os.name == "nt":
            bit_v = platform.architecture()[0]
            lib_path = os.path.join(module_path, self.__LIB_WIN.format(bit_v))
        else:
            lib_path = os.path.join(module_path, self.__LIB_UNIX)

        self._api = CDLL(lib_path)
        self._check_library_loaded()
        self._interfaces = {}
        # change the restype due to windows specific behavior
        self._api.rr_init_interface.restype = c_void_p
        self._api.rr_init_servo.restype = c_void_p
        # change the restype to return value not pointer
        self._api.rr_describe_emcy_bit.restype = c_char_p
        self._api.rr_describe_emcy_code.restype = c_char_p
        self._api.rr_describe_nmt.restype = c_char_p
        # change the restype to return structure pointer
        self._api.rr_emcy_log_pop.restype = POINTER(EmcyObject)

    def _check_library_loaded(self):
        if self._api is None:
            raise AttributeError(
                "Impossible to load the library. Go back to the building "
                "instructions and execute `make python` first."
            )

    @property
    def api(self):
        self._check_library_loaded()
        return self._api

    def init_interface(self, interface_name: str) -> Interface:
        """The function is the second to call (after api initialization) to be able to work with the user API.

        It opens the COM port where the corresponding CAN-USB dongle is connected, enabling communication between the
        user program and the servo motors on the respective CAN bus.

        Examples of an interface name string:
            * Linux: "/dev/ttyACM0" **or** "/dev/serial/by-id/usb-Rozum_Robotics_USB-CAN_Interface_301-if00"
            * MacOS: "/dev/cu.modem301"
            * Windows (Cygwin): "/dev/ttyS0"
        *Note: last numbers in "/dev/.." strings may differ on your machine.*

        :param interface_name: str
        :return: Interface instance
        """
        self._check_library_loaded()
        if interface_name not in self._interfaces:
            interface = Interface(self._api, interface_name)
            if interface is None:
                raise AttributeError(
                    "Failed to initialize interface named: {}.".format(
                        interface_name
                    )
                )

            self._interfaces[interface_name] = interface
        return self._interfaces[interface_name]

    def sleep_ms(self, ms: int):
        """The function sets an idle period for the user program (e.g., to wait till a servo executes a motion trajectory).

        Until the period expires, the user program will not execute any further operations.
        However, the network management, CAN communication, emergency, and Heartbeat functions remain available.
        Note:The user can also call system-specific sleep functions directly.
        However, using this sleep function is preferable to ensure compatibility with subsequent API library versions.

        :param ms: int:
            Idle period (in milleseconds)
        :return: None
        """
        self._api.rr_sleep_ms(c_int(ms))

    def describe_emcy_bit(self, bit: int):
        """The function returns a string describing in detail a specific EMCY event based on the code in the 'bit'
        parameter (e.g., "CAN bus warning limit reached"). The function can be used in combination with the
        describe_emcy_code. The latter provides a more generic description of an EMCY event.

        :param bit: int:
            Error bit field of the corresponding EMCY message (according to the CanOpen standard)
        :return: Description: str
        """
        return self._api.rr_describe_emcy_bit(bit).decode("utf-8")

    def describe_emcy_code(self, code: int):
        """The function returns a string descibing a specific EMCY event based on the error code in the 'code'
        parameter. The description in the string is a generic type of the occured emergency event (e.g., "Temperature").
        For a more detailed description, use the function together with the describe_emcy_bit one.

        :param code: int
            Error code from the corresponding EMCY message (according to the CanOpen standard)
        :return: Description: str
        """
        return self._api.rr_describe_emcy_code(code).decode("utf-8")

    def describe_nmt_state(self, code: int):
        """ The function returns a string describing the NMT state code
        specified in the 'state' parameter.

        :param code: int: state NMT state code to descibe
        :return: Description: str
        """
        return self._api.rr_describe_nmt(code).decode("utf-8")

    def __del__(self):
        for interface in self._interfaces.values():
            interface.deinit_interface()
