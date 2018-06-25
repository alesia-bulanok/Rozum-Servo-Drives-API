/**
 * @brief Tutorial example of reading motion queue parameters
 * 
 * @file read_servo_motion_queue.c
 * @author Rozum
 * @date 2018-06-25
 */

#include "api.h"
#include "tutorial.h"

/**
 * @brief Tutorial example of reading motion queue parameters
 * 
 * @ingroup tutor_c_read_motion_queue
 */
int main(int argc, char *argv[])
{
    /** @code{.c} 
    */
    rr_can_interface_t *iface = rr_init_interface(TUTORIAL_DEVICE);
    rr_servo_t *servo = rr_init_servo(iface, TUTORIAL_SERVO_0_ID);

    API_DEBUG("========== Tutorial of the %s ==========\n", "reading motion queue parameters");

    API_DEBUG("Clearing points\n");
    rr_clear_points_all(servo);

    uint32_t num;
    rr_get_points_size(servo, &num);
    API_DEBUG("\tPoints in the queue before: %d\n", num);

    rr_get_points_free_space(servo, &num);
    API_DEBUG("\tPoints queue free size before: %d\n", num);

    API_DEBUG("Appending points\n");
    rr_add_motion_point(servo, 0.0, 0.0, 10000000);
    rr_add_motion_point(servo, 0.0, 0.0, 10000000);

    rr_get_points_size(servo, &num);
    API_DEBUG("\tPoints in the queue after: %d\n", num);

    rr_get_points_free_space(servo, &num);
    API_DEBUG("\tPoints queue free size after: %d\n", num);
    /** @endcode */
}
