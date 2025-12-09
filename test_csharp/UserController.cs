using Microsoft.AspNetCore.Mvc;
using MyApp.Services;

namespace MyApp.Controllers
{
    [ApiController]
    [Route("api/[controller]")]
    public class UserController : ControllerBase
    {
        private readonly IUserService _userService;
        private readonly ILogger<UserController> _logger;

        public UserController(IUserService userService, ILogger<UserController> logger)
        {
            _userService = userService;
            _logger = logger;
        }

        [HttpGet]
        public async Task<IActionResult> GetUsers()
        {
            _logger.LogInformation("Getting all users");
            var users = await _userService.GetAllUsersAsync();
            
            if (users == null || !users.Any())
            {
                return NotFound("No users found");
            }
            
            return Ok(users);
        }

        [HttpPost]
        public async Task<IActionResult> CreateUser([FromBody] CreateUserRequest request)
        {
            if (request == null)
            {
                return BadRequest("Invalid user data");
            }

            var userId = await _userService.CreateUserAsync(request);
            return CreatedAtAction(nameof(GetUsers), new { id = userId }, request);
        }
    }
}
