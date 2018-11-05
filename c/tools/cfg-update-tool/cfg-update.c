#include "logging.h"
#include "usbcan_proto.h"
#include "usbcan_types.h"
#include "usbcan_util.h"
#include "loader_proto.h"
#include "crc32.h"
#include "parson.h"
#include "util.h"

#include <getopt.h>
#include <dirent.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <unistd.h>

#ifdef _WIN32
#define DIR_SEPARATOR "\\"
#else
#define DIR_SEPARATOR "/"
#endif

char *dir_name = NULL;

usbcan_instance_t *inst;
usbcan_device_t *dev;

uint32_t cfg_hw, cfg_rev, dev_hw, dev_rev;
static bool update_all = false;
bool master_hb_inhibit = true;

uint32_t release(usbcan_device_t *dev)
{
    uint8_t data = 0;
    return write_raw_sdo(dev, 0x2010, 0x01, &data, sizeof(data), 1, 100);
}

bool update(usbcan_device_t *dev, char *name)
{
	JSON_Value *root_value;
	JSON_Object *root_object;
	JSON_Array *settings;
	//const char *cfg_fw;
	int idx;

	LOG_INFO(debug_log, "Checking settings file '%s' compatibility", name);

	root_value = json_parse_file(name);
	root_object = json_value_get_object(root_value);

	if(!json_object_has_value(root_object, "ID") || !json_object_has_value(root_object, "Settings"))
	{
		LOG_WARN(debug_log, "Wrong file format");
		return false;
	}

	//cfg_fw = json_object_dotget_string(root_object, "ID.FW");
	cfg_hw = atoi(json_object_dotget_string(root_object, "ID.HW"));
	cfg_rev = atoi(json_object_dotget_string(root_object, "ID.REV"));

	LOG_INFO(debug_log, "Config file identity: Hardware: %"PRIu32", revision: %"PRIu32, cfg_hw, cfg_rev);

	if((cfg_hw != dev_hw) || (cfg_rev != dev_rev))
	{
		LOG_WARN(debug_log, "Not compatible settings");
		return false;
	}
	else
	{
		LOG_INFO(debug_log, "Suitable config found");
	}

	settings = json_object_get_array(root_object, "Settings");

	for(idx = 0; idx < json_array_get_count(settings); idx++)
	{
		JSON_Object *entry = json_value_get_object(json_array_get_value(settings, idx));

		const char *name = json_object_get_string(entry, "Name");
		uint16_t sdo_idx = json_object_get_number(entry, "Index");
		uint8_t sdo_sidx = json_object_get_number(entry, "SubIndex");
		JSON_Array *jvalue = json_object_get_array(entry, "Value");
		int sz = json_array_get_count(jvalue);
		uint8_t value[sz];

		LOG_INFO(debug_log, "Writing %d byte(s) to '%s' 0x%"PRIx16" %"PRIu8"", sz, name, sdo_idx, sdo_sidx);

		for(int i = 0; i < sz; i++)
		{
			value[i] = json_array_get_number(jvalue, i);
		}

		write_raw_sdo(dev, sdo_idx, sdo_sidx, value, sz, 1, 100);
	}

	LOG_INFO(debug_log, "Saving to flash");
	
	uint32_t store_pass = PARAM_STORE_PASSWORD;
	write_raw_sdo(dev, CO_OD_INDEX_STORE_PARAMETERS, 
		CO_OD_SUBINDEX_1_STORE_PARAMETERS_SAVE_ALL_PARAMETERS, 
		(uint8_t *)&store_pass, sizeof(store_pass), 1, 2000);

	LOG_INFO(debug_log, "Resetting device");
	write_nmt(dev->inst, dev->id, CO_NMT_CMD_RESET_NODE); 
	LOG_INFO(debug_log, "Waitng to finish reset...");
	if(!wait_device(dev->inst, dev->id, 5000))
	{
		LOG_ERROR(debug_log, "Can't find device on bus");
	}
	else
	{
		LOG_INFO(debug_log, "Rest finished");
	}

	return true;
}

void usage(char **argv)
{
	fprintf(stdout,	"Usage: %s\n"
			"    port\n"
			"    id or 'all'\n"
			"    -C(--config-dir) config_folder_path\n"
			"    [-M(--master-hb)]\n"
			"\n",
			argv[0]);
}

bool parse_cmd_line(int argc, char **argv)
{
	int c;
	int option_index = 0;
	static struct option long_options[] = 
	{
		{"config-dir",     required_argument, 0, 'C' },
		{"master-hb",     optional_argument, 0, 'M' },
		{0,         0,                 0,  0 }
	};

	while (1) 
	{
		c = getopt_long(argc, argv, "-:C:M", long_options, &option_index);
		if (c == -1)
		{
			break;
		}

		switch (c) 
		{
			case 'C':
				dir_name = optarg;
				break;

			case 'M':
				LOG_INFO(debug_log, "Enabling master hearbeat");
				master_hb_inhibit = false;
				break;

			default:
				break;
		}
	}

	if(!dir_name)
	{
		return false;
	}

	return true;
}

void do_update(int id)
{
	DIR *dir;
	char *name = 0;
	struct stat s;
	struct dirent *entry;
	int len;
	
	do
	{
		dev = usbcan_device_init(inst, id);
		if(!dev)
		{
			LOG_ERROR(debug_log, "Can't create device instance\n");
		}

		len = 4;
		if(read_raw_sdo(dev, 0x1018, 2, (uint8_t *)&dev_hw, &len, 1, 100))
		{
			LOG_ERROR(debug_log, "Can't read device HW type");
			break;
		}
		len = 4;
		if(read_raw_sdo(dev, 0x1018, 3, (uint8_t *)&dev_rev, &len, 1, 100))
		{
			LOG_ERROR(debug_log, "Can't read device revision");
			break;
		}

		LOG_INFO(debug_log, "Device identity: Hardware: %"PRIu32", revision: %"PRIu32, dev_hw, dev_rev);

		if(!(dir = opendir(dir_name)))
		{
			LOG_ERROR(debug_log, "Can't open config folder in '%s'", dir_name);
			break;
		}

		while((entry = readdir(dir)) != NULL)
		{
			name = realloc(name, strlen(entry->d_name) + strlen(dir_name) + 2);
			sprintf(name, "%s"DIR_SEPARATOR"%s", dir_name, entry->d_name);
			stat(name, &s);
			if(!S_ISDIR(s.st_mode))
			{
				char *dot = strchr(entry->d_name, '.');
				if(dot && (strcmp(dot, ".jsonconfig") == 0))
				{
					if(update(dev, name))
					{
						break;
					}
				}
				else
				{
					LOG_WARN(debug_log, "Not a settings file '%s'", entry->d_name);
				}
			}
		}
	}
	while(0);

	if(name)
	{
		free(name);
	}
	
	usbcan_device_deinit(&dev);	
}

int main(int argc, char **argv)
{
	int id = 0;
	
	debug_log = stdout;
	
	if(!parse_cmd_line(argc, argv))
	{
		usage(argv);
		exit(1);
	}
	
	inst = usbcan_instance_init(argv[1]);
	if(!inst)
	{
		LOG_ERROR(debug_log, "Can't create usbcan instance\n");
		exit(1);
	}
	
		if(strcmp(argv[2], "all") != 0)
	{
		update_all = false;
		id = strtol(argv[2], 0, 0);
	}
	else
	{
		update_all = true;
	}

	usbcan_inhibit_master_hb(inst, master_hb_inhibit);

	LOG_INFO(debug_log, "Updating firmware");
	
	if(update_all)
	{		
		LOG_INFO(debug_log, "Discovering devices...");
		msleep(5000);
	}

	if(update_all)
	{
		for(int i = 0; i < USB_CAN_MAX_DEV; i++)
		{
			if(inst->dev_alive[i] >= 0)
			{
				LOG_INFO(debug_log, "Updating device %d", i);
				do_update(i);
			}
		}
	}
	else
	{
		do_update(id);
	}

	
	return 0;
}
