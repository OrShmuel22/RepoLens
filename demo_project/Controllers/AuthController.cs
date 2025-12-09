using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Authorization;
using System.Threading.Tasks;
using DemoApp.Services;
using DemoApp.Models;

namespace DemoApp.Controllers
{
    [ApiController]
    [Route("api/[controller]")]
    public class AuthController : ControllerBase
    {
        private readonly IAuthenticationService _authService;
        private readonly ILogger<AuthController> _logger;

        public AuthController(IAuthenticationService authService, ILogger<AuthController> logger)
        {
            _authService = authService;
            _logger = logger;
        }

        [HttpPost("login")]
        [AllowAnonymous]
        public async Task<IActionResult> Login([FromBody] LoginRequest request)
        {
            if (string.IsNullOrEmpty(request.Username) || string.IsNullOrEmpty(request.Password))
            {
                return BadRequest("Username and password are required");
            }

            var result = await _authService.LoginAsync(request.Username, request.Password);

            if (!result.Succeeded)
            {
                return Unauthorized(new { message = result.ErrorMessage });
            }

            return Ok(new 
            { 
                token = result.Token,
                user = new 
                {
                    id = result.User.Id,
                    username = result.User.Username,
                    email = result.User.Email
                }
            });
        }

        [HttpPost("logout")]
        [Authorize]
        public async Task<IActionResult> Logout()
        {
            var userId = User.FindFirst("sub")?.Value;
            await _authService.LogoutAsync(userId);
            
            return Ok(new { message = "Logged out successfully" });
        }

        [HttpGet("validate")]
        public async Task<IActionResult> ValidateToken([FromHeader(Name = "Authorization")] string authorization)
        {
            if (string.IsNullOrEmpty(authorization))
            {
                return Unauthorized();
            }

            var token = authorization.Replace("Bearer ", "");
            var isValid = await _authService.ValidateTokenAsync(token);

            if (!isValid)
            {
                return Unauthorized();
            }

            return Ok(new { valid = true });
        }
    }
}
